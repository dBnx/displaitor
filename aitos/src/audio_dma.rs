//! Owned hardware-paced PWM and DMA, with interrupt-backed completion waits.
//!
//! Data channels chain to one final midpoint sample unless a complete successor
//! is linked. Commands drain prepared samples instead of aborting DMA, retaining
//! the exact decoder position across mute. No task polls sample deadlines.
use aitos::audio::{
    BLOCK_SAMPLES, SILENCE_WORD, dma_transfer_completed, successor_needs_fresh_start,
};
use core::sync::atomic::AtomicU32;
use core::{
    future::poll_fn,
    sync::atomic::{Ordering, compiler_fence},
    task::Poll,
};
use embassy_rp::{
    Peri,
    interrupt::{self, InterruptExt},
    pac::{
        self,
        dma::regs::CtrlTrig,
        dma::vals::{DataSize, TreqSel},
    },
    peripherals::{DMA_CH2, DMA_CH3, DMA_CH4},
    pwm::Pwm,
};
use embassy_sync::waitqueue::AtomicWaker;
use static_cell::ConstStaticCell;

pub type AudioPwm = Pwm<'static>;
pub type AudioChannels = (
    Peri<'static, DMA_CH2>,
    Peri<'static, DMA_CH3>,
    Peri<'static, DMA_CH4>,
);
type Block = [u32; BLOCK_SAMPLES];
static BLOCK_A: ConstStaticCell<Block> = ConstStaticCell::new([SILENCE_WORD; BLOCK_SAMPLES]);
static BLOCK_B: ConstStaticCell<Block> = ConstStaticCell::new([SILENCE_WORD; BLOCK_SAMPLES]);
static SILENCE: u32 = SILENCE_WORD;
static DMA_COMPLETED: AtomicWaker = AtomicWaker::new();
// Core-1 IRQ publishes completion before clearing the raw IRQ bit. The task
// clears both only while that channel is idle and unreachable by a chain.
static COMPLETION_SEEN: [AtomicU32; 3] = [const { AtomicU32::new(0) }; 3];
const AUDIO_CHANNEL_MASK: u32 = (1 << 2) | (1 << 3) | (1 << 4);

/// Profiling-only, cumulative SWD evidence: data completions (channels 2/3),
/// fallback completions (channel 4), last DMA_TIMER0 word observed in the IRQ,
/// and underrun recoveries. Counters saturate and are never reset during a run.
/// Core 1 alone writes each word; IRQ/task writers use different indices, so
/// load/store updates need neither atomic read-modify-write nor another lock.
#[cfg(feature = "profiling")]
#[unsafe(no_mangle)]
pub static AUDIO_DIAGNOSTICS: [AtomicU32; 4] = [const { AtomicU32::new(0) }; 4];

/// Profiling-only capture request/result: duration request, actual start/end
/// timer-low timestamps, four baseline diagnostics, and four final diagnostics.
/// The sampler accepts one request, settles for 100 ms after probe attachment,
/// then captures while both CPUs run. It publishes end_us last. Submit another
/// request only after reading the previous result; zero end_us means pending.
#[cfg(feature = "profiling")]
#[unsafe(no_mangle)]
pub static AUDIO_CAPTURE: [AtomicU32; 11] = [const { AtomicU32::new(0) }; 11];
#[cfg(feature = "profiling")]
static CAPTURE_PHASE: AtomicU32 = AtomicU32::new(0);
#[cfg(feature = "profiling")]
static CAPTURE_DEADLINE: AtomicU32 = AtomicU32::new(0);
#[cfg(feature = "profiling")]
static CAPTURE_DURATION: AtomicU32 = AtomicU32::new(0);

/// Called only by the existing core-0 1 kHz sampler. Private state therefore
/// needs no new lock, read-modify-write, timer alarm, or executor wakeup.
#[cfg(feature = "profiling")]
pub fn profile_capture_tick(now_us: u32) {
    let phase = CAPTURE_PHASE.load(Ordering::Relaxed);
    if phase == 0 {
        let requested = AUDIO_CAPTURE[0].load(Ordering::Acquire);
        if requested != 0 {
            AUDIO_CAPTURE[1].store(0, Ordering::Relaxed);
            AUDIO_CAPTURE[2].store(0, Ordering::Relaxed);
            // Wrapping comparisons remain unambiguous below half a timer wrap.
            CAPTURE_DURATION.store(requested.min(i32::MAX as u32), Ordering::Relaxed);
            CAPTURE_DEADLINE.store(now_us.wrapping_add(100_000), Ordering::Relaxed);
            CAPTURE_PHASE.store(1, Ordering::Relaxed);
            AUDIO_CAPTURE[0].store(0, Ordering::Release);
        }
        return;
    }
    let deadline = CAPTURE_DEADLINE.load(Ordering::Relaxed);
    if now_us.wrapping_sub(deadline) >= 1 << 31 {
        return;
    }
    if phase == 1 {
        for (output, counter) in AUDIO_CAPTURE[3..7].iter().zip(&AUDIO_DIAGNOSTICS) {
            output.store(counter.load(Ordering::Relaxed), Ordering::Relaxed);
        }
        AUDIO_CAPTURE[1].store(now_us, Ordering::Relaxed);
        CAPTURE_DEADLINE.store(
            now_us.wrapping_add(CAPTURE_DURATION.load(Ordering::Relaxed)),
            Ordering::Relaxed,
        );
        CAPTURE_PHASE.store(2, Ordering::Relaxed);
    } else {
        for (output, counter) in AUDIO_CAPTURE[7..11].iter().zip(&AUDIO_DIAGNOSTICS) {
            output.store(counter.load(Ordering::Relaxed), Ordering::Relaxed);
        }
        AUDIO_CAPTURE[2].store(now_us, Ordering::Release);
        CAPTURE_PHASE.store(0, Ordering::Relaxed);
    }
}

#[cfg(feature = "profiling")]
fn profile_add(index: usize, amount: u32) {
    let counter = &AUDIO_DIAGNOSTICS[index];
    counter.store(
        counter.load(Ordering::Relaxed).saturating_add(amount),
        Ordering::Relaxed,
    );
}

// Only core 1 unmasks this vector. HUB75 owns DMA_IRQ_1 and channels 0/1.
#[unsafe(no_mangle)]
extern "C" fn DMA_IRQ_0() {
    let pending = pac::DMA.ints(0).read() & AUDIO_CHANNEL_MASK;
    if pending != 0 {
        for index in 2..=4 {
            assert!(
                !pac::DMA.ch(index).ctrl_trig().read().ahb_error(),
                "audio DMA bus error"
            );
            if pending & (1 << index) != 0 {
                COMPLETION_SEEN[index - 2].store(1, Ordering::Release);
            }
        }
        #[cfg(feature = "profiling")]
        {
            let data = (pending & ((1 << 2) | (1 << 3))).count_ones();
            if data != 0 {
                profile_add(0, data);
            }
            if pending & (1 << 4) != 0 {
                profile_add(1, 1);
            }
            AUDIO_DIAGNOSTICS[2].store(pac::DMA.timer(0).read().0, Ordering::Relaxed);
        }
        // W1C only our channels; never consume another DMA user's status.
        compiler_fence(Ordering::SeqCst);
        pac::DMA.intr(0).write_value(pending);
        DMA_COMPLETED.wake();
    }
}

pub struct AudioDma {
    // Retained lifetime ownership: raw register programming never creates a
    // second HAL channel or aliases another peripheral owner.
    _pwm: AudioPwm,
    _channels: AudioChannels,
    blocks: [&'static mut Block; 2],
    current: Option<usize>,
    queued: Option<usize>,
    free: [bool; 2],
    segment_started: bool,
}

impl AudioDma {
    pub fn new(pwm: AudioPwm, channels: AudioChannels, system_clock_hz: u32) -> Self {
        assert_eq!(
            embassy_rp::multicore::current_core(),
            embassy_rp::multicore::CoreId::Core1
        );
        // 125 MHz * 4 / 15625 is exactly 32 kHz.
        assert_eq!(system_clock_hz, 125_000_000);
        let output = Self {
            _pwm: pwm,
            _channels: channels,
            blocks: [BLOCK_A.take(), BLOCK_B.take()],
            current: None,
            queued: None,
            free: [true; 2],
            segment_started: false,
        };
        output.set_timer(false);
        output.midpoint();
        output.configure_silence();
        output.clear_credits();
        pac::DMA.intr(0).write_value(AUDIO_CHANNEL_MASK);
        // Preserve other owners' enables even if another core arms its line
        // concurrently. Embassy's private RegExt is unavailable to adapters.
        critical_section::with(|_| {
            pac::DMA.inte(0).modify(|w| *w |= AUDIO_CHANNEL_MASK);
        });
        interrupt::DMA_IRQ_0.unpend();
        // SAFETY: owned channels and completion state are initialized. Only
        // core 1 enables this NVIC line; the handler accesses no task-owned data.
        unsafe { interrupt::DMA_IRQ_0.enable() };
        output
    }

    fn data(&self, index: usize) -> pac::dma::Channel {
        assert!(index < 2);
        pac::DMA.ch(index + 2)
    }
    fn busy(&self, index: usize) -> bool {
        self.data(index).ctrl_trig().read().busy()
    }
    fn remaining(&self, index: usize) -> u32 {
        self.data(index).trans_count().read()
    }
    fn completed(&self, index: usize) -> bool {
        let remaining = self.remaining(index);
        dma_transfer_completed(
            self.busy(index),
            remaining,
            Self::completion_seen(index + 2),
        )
    }
    fn completion_seen(channel: usize) -> bool {
        // Read raw status BEFORE the software latch. If the IRQ preempts this
        // read, its latch is set before W1C, so completion cannot disappear.
        let pending = pac::DMA.intr(0).read() & (1 << channel) != 0;
        compiler_fence(Ordering::SeqCst);
        pending || COMPLETION_SEEN[channel - 2].load(Ordering::Acquire) != 0
    }
    fn clear_completion(channel: usize) {
        // The owner calls this only for an idle, unreachable channel. W1C first
        // prevents an old pending IRQ from re-setting the newly cleared latch.
        pac::DMA.intr(0).write_value(1 << channel);
        COMPLETION_SEEN[channel - 2].store(0, Ordering::Release);
    }
    fn set_timer(&self, enabled: bool) {
        // DMA pacing timer 0 is reserved exclusively for this owner.
        pac::DMA.timer(0).write(|w| {
            w.set_x(if enabled { 4 } else { 0 });
            w.set_y(15625);
        });
    }
    fn clear_credits(&self) {
        // Called only with all three owned channels idle.
        for index in 2..=4 {
            pac::DMA.ch(index).dbg_ctdreq().write(|w| w.0 = 0);
        }
    }
    fn destination(&self) -> u32 {
        pac::PWM.ch(5).cc().as_ptr() as u32
    }
    fn midpoint(&self) {
        // Whole PWM5 ownership is retained. Full-word writes avoid RP2040's
        // replicated narrow peripheral writes; channel A is unused.
        pac::PWM.ch(5).cc().write(|w| w.set_b(127));
    }
    fn control(chain: u8, increment: bool) -> CtrlTrig {
        let mut ctrl = CtrlTrig(0);
        ctrl.set_data_size(DataSize::SIZE_WORD);
        ctrl.set_incr_read(increment);
        ctrl.set_treq_sel(TreqSel::from_bits(0x3b));
        ctrl.set_chain_to(chain);
        // Every data/fallback completion wakes the decoder/drain future.
        ctrl.set_irq_quiet(false);
        ctrl.set_en(true);
        ctrl
    }
    fn modify_control(channel: pac::dma::Channel, f: impl FnOnce(&mut CtrlTrig)) {
        // Use the non-triggering alias; a CTRL_TRIG write would restart DMA.
        channel.al1_ctrl().modify(|raw| {
            let mut ctrl = CtrlTrig(*raw);
            f(&mut ctrl);
            *raw = ctrl.0;
        });
    }
    fn configure_silence(&self) {
        let channel = pac::DMA.ch(4);
        Self::clear_completion(4);
        channel.al1_ctrl().write_value(Self::control(4, false).0);
        channel
            .read_addr()
            .write_value((&SILENCE as *const u32) as u32);
        channel.write_addr().write_value(self.destination());
        channel.trans_count().write_value(1);
    }
    async fn wait_completed(&self, index: usize) {
        poll_fn(|cx| {
            DMA_COMPLETED.register(cx.waker());
            if self.completed(index) {
                Poll::Ready(())
            } else {
                Poll::Pending
            }
        })
        .await;
        cortex_m::asm::dsb();
        compiler_fence(Ordering::SeqCst);
    }
    async fn wait_silence(&self) {
        poll_fn(|cx| {
            DMA_COMPLETED.register(cx.waker());
            let channel = pac::DMA.ch(4);
            let remaining = channel.trans_count().read();
            if dma_transfer_completed(
                channel.ctrl_trig().read().busy(),
                remaining,
                Self::completion_seen(4),
            ) {
                Poll::Ready(())
            } else {
                Poll::Pending
            }
        })
        .await;
        cortex_m::asm::dsb();
        compiler_fence(Ordering::SeqCst);
    }
    fn configure_data(&self, index: usize) {
        // The channel is free and unreachable. Its source is static SRAM held
        // exclusively until a completion event, count=0 and !BUSY agree.
        cortex_m::asm::dsb();
        compiler_fence(Ordering::SeqCst);
        let channel = self.data(index);
        Self::clear_completion(index + 2);
        channel.al1_ctrl().write_value(Self::control(4, true).0);
        channel
            .read_addr()
            .write_value(self.blocks[index].as_ptr() as u32);
        channel.write_addr().write_value(self.destination());
        channel.trans_count().write_value(BLOCK_SAMPLES as u32);
        channel.dbg_ctdreq().write(|w| w.0 = 0);
    }
    async fn start_or_resume(&mut self, index: usize) -> bool {
        Self::modify_control(self.data(index), |w| w.set_en(false));
        // The first block has never been triggered. Later links may already
        // have started or even completed while the CPU was delayed.
        if self.segment_started
            && !successor_needs_fresh_start(self.busy(index), Self::completion_seen(index + 2))
        {
            Self::modify_control(self.data(index), |w| w.set_en(true));
            return false;
        }
        if self.segment_started {
            // A late trigger into a disabled successor can miss the fallback.
            // Start an uncompleted fallback if necessary; a BUSY channel
            // ignores another trigger. Do not retrigger a completed fallback.
            if !Self::completion_seen(4) {
                pac::DMA.multi_chan_trigger().write(|w| w.0 = 1 << 4);
            }
            self.wait_silence().await;
        }
        self.set_timer(false);
        self.midpoint();
        self.clear_credits();
        self.configure_silence();
        Self::modify_control(self.data(index), |w| w.set_en(true));
        pac::DMA
            .multi_chan_trigger()
            .write(|w| w.0 = 1 << (index + 2));
        self.set_timer(true);
        self.segment_started = true;
        true
    }

    pub fn buffer(&mut self, index: usize) -> &mut Block {
        assert!(self.free[index]);
        self.blocks[index]
    }

    /// Queue a complete block. Returns true after recovery from an underrun.
    pub async fn queue(&mut self, index: usize) -> bool {
        assert!(self.free[index] && self.queued.is_none());
        self.configure_data(index);
        self.free[index] = false;
        if let Some(current) = self.current {
            // A just-chained channel can be configured but not BUSY yet. In the
            // rare case we observe that window, await its completion instead of
            // guessing whether its trigger arrived. Recovery retains every
            // sample, with silence if the handoff deadline has passed.
            if !self.busy(current) && !Self::completion_seen(current + 2) {
                self.wait_completed(current).await;
            }
            Self::modify_control(self.data(current), |w| {
                w.set_chain_to((index + 2) as u8);
                w.set_en(false);
            });
            let underrun = if !self.busy(current) {
                self.start_or_resume(index).await
            } else {
                Self::modify_control(self.data(current), |w| w.set_en(true));
                false
            };
            self.queued = Some(index);
            #[cfg(feature = "profiling")]
            if underrun {
                profile_add(3, 1);
            }
            underrun
        } else {
            self.start_or_resume(index).await;
            self.current = Some(index);
            false
        }
    }

    fn reclaim(&mut self) -> Option<usize> {
        let current = self.current?;
        if !self.completed(current) {
            return None;
        }
        cortex_m::asm::dsb();
        compiler_fence(Ordering::SeqCst);
        self.current = self.queued.take();
        self.free[current] = true;
        Some(current)
    }
    pub async fn next_completed(&mut self) -> Option<usize> {
        let current = self.current?;
        self.wait_completed(current).await;
        self.reclaim()
    }
    pub fn active(&self) -> bool {
        self.current.is_some()
    }
    /// Drain at most two 2 ms blocks and the final fallback sample tick.
    pub async fn drain(&mut self) {
        while self.next_completed().await.is_some() {}
        if self.segment_started {
            self.wait_silence().await;
        }
        self.set_timer(false);
        self.midpoint();
        self.clear_credits();
        self.segment_started = false;
    }
}
