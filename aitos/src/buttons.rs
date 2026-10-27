//! High-priority core-0 sampling, independent of rendering and USB backpressure.
use aitos::input::{Batch, Cadence, Sampler};
use core::{
    cell::RefCell,
    sync::atomic::{AtomicU32, Ordering},
};
use cortex_m::interrupt::Mutex;
use displaitor::Controls;
use embassy_rp::{
    gpio::Input,
    multicore::{CoreId, current_core},
};
use embassy_sync::{blocking_mutex::raw::CriticalSectionRawMutex, signal::Signal};
use embassy_time::{Instant, Timer};

const CAPACITY: usize = 32;
pub struct Pins {
    pub a: Input<'static>,
    pub b: Input<'static>,
    pub select: Input<'static>,
    pub up: Input<'static>,
    pub down: Input<'static>,
    pub left: Input<'static>,
    pub right: Input<'static>,
}
impl Pins {
    fn read(&self) -> Controls {
        Controls {
            buttons_a: self.a.is_low(),
            buttons_b: self.b.is_low(),
            buttons_s: self.select.is_low(),
            dpad_up: self.up.is_low(),
            dpad_down: self.down.is_low(),
            dpad_left: self.left.is_low(),
            dpad_right: self.right.is_low(),
        }
    }
}
// All accesses are on core 0, protected against its interrupt executor.
static INPUT: Mutex<RefCell<Option<Sampler<CAPACITY>>>> = Mutex::new(RefCell::new(None));
static CHANGED: Signal<CriticalSectionRawMutex, ()> = Signal::new();
// Missed deadlines, dropped transitions, maximum sampling interval in microseconds.
#[unsafe(no_mangle)]
pub static INPUT_DIAGNOSTICS: [AtomicU32; 3] = [const { AtomicU32::new(0) }; 3];
pub fn init() -> u64 {
    assert_eq!(current_core(), CoreId::Core0);
    let now = Instant::now().as_micros();
    cortex_m::interrupt::free(|cs| {
        let mut state = INPUT.borrow(cs).borrow_mut();
        assert!(state.is_none(), "button sampler starts once");
        *state = Some(Sampler::new(now));
    });
    now
}
#[embassy_executor::task]
pub async fn run(pins: Pins, started_us: u64) -> ! {
    let mut cadence = Cadence::new(started_us);
    let mut sampled_us = started_us;
    loop {
        Timer::at(Instant::from_micros(cadence.next_us())).await;
        let now = Instant::now().as_micros();
        let raw = pins.read();
        #[cfg(feature = "profiling")]
        let raw = {
            let synthetic = super::profiling::input();
            Controls {
                buttons_a: raw.buttons_a || synthetic.buttons_a,
                buttons_b: raw.buttons_b || synthetic.buttons_b,
                buttons_s: raw.buttons_s || synthetic.buttons_s,
                dpad_up: raw.dpad_up || synthetic.dpad_up,
                dpad_down: raw.dpad_down || synthetic.dpad_down,
                dpad_left: raw.dpad_left || synthetic.dpad_left,
                dpad_right: raw.dpad_right || synthetic.dpad_right,
            }
        };
        let changed = cortex_m::interrupt::free(|cs| {
            let mut state = INPUT.borrow(cs).borrow_mut();
            let input = state.as_mut().expect("sampler initialized");
            let changed = input.sample(now, raw);
            INPUT_DIAGNOSTICS[1].store(input.dropped(), Ordering::Relaxed);
            changed
        });
        cadence.sampled(now);
        INPUT_DIAGNOSTICS[0].store(cadence.missed(), Ordering::Relaxed);
        let interval = now.saturating_sub(sampled_us).min(u64::from(u32::MAX)) as u32;
        INPUT_DIAGNOSTICS[2].store(
            INPUT_DIAGNOSTICS[2].load(Ordering::Relaxed).max(interval),
            Ordering::Relaxed,
        );
        sampled_us = now;
        #[cfg(feature = "profiling")]
        super::audio_dma::profile_capture_tick(now as u32);
        if changed {
            CHANGED.signal(());
        }
    }
}
pub async fn changed() {
    CHANGED.wait().await;
}
pub fn drain() -> Batch<CAPACITY> {
    assert_eq!(current_core(), CoreId::Core0);
    cortex_m::interrupt::free(|cs| {
        let cutoff = Instant::now().as_micros();
        INPUT
            .borrow(cs)
            .borrow_mut()
            .as_mut()
            .expect("sampler initialized")
            .drain(cutoff)
    })
}
