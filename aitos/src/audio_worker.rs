//! Core 1 decodes ahead of hardware-paced PWM. Completion interrupts and changed
//! commands wake the executor; an idle or muted player consumes no polling loop.
use super::audio_dma::{AudioChannels, AudioDma, AudioPwm};
use aitos::audio::{CommandMailbox, OUTPUT_RATE, OutputPlayer, SILENCE_WORD};
use core::cell::RefCell;
use critical_section::Mutex;
use displaitor::AudioId;
use embassy_sync::{blocking_mutex::raw::CriticalSectionRawMutex, signal::Signal};

static COMMANDS: Mutex<RefCell<CommandMailbox>> = Mutex::new(RefCell::new(CommandMailbox::new()));
static COMMAND_CHANGED: Signal<CriticalSectionRawMutex, ()> = Signal::new();

pub fn request(clip: Option<AudioId>, enabled: bool) {
    let changed =
        critical_section::with(|cs| COMMANDS.borrow(cs).borrow_mut().request(clip, enabled));
    if changed {
        COMMAND_CHANGED.signal(());
    }
}

fn take_commands() -> (Option<AudioId>, bool) {
    critical_section::with(|cs| COMMANDS.borrow(cs).borrow_mut().take())
}
fn apply(player: &mut OutputPlayer, (clip, enabled): (Option<AudioId>, bool)) {
    player.set_enabled(enabled);
    if let Some(clip) = clip
        && player.select(clip).is_err()
    {
        defmt::error!("Invalid audio asset");
    }
}

#[embassy_executor::task]
pub async fn run(pwm: AudioPwm, channels: AudioChannels, system_clock_hz: u32) -> ! {
    let mut dma = AudioDma::new(pwm, channels, system_clock_hz);
    let mut player = OutputPlayer::new(OUTPUT_RATE);
    'playback: loop {
        // Clear notification BEFORE consuming its state: a later producer either
        // appears in this snapshot or leaves a signal for the next idle wait.
        COMMAND_CHANGED.reset();
        apply(&mut player, take_commands());
        if !player.is_playing() {
            COMMAND_CHANGED.wait().await;
            continue;
        }
        match player.fill_pwm(dma.buffer(0)) {
            Ok(true) => {}
            Ok(false) => continue,
            Err(_) => {
                defmt::error!("QOA decode failed");
                continue;
            }
        }
        let mut ended = !player.is_playing();
        let second = if ended {
            false
        } else {
            match player.fill_pwm(dma.buffer(1)) {
                Ok(has_audio) => has_audio,
                Err(_) => {
                    defmt::error!("QOA decode failed");
                    continue;
                }
            }
        };
        ended |= !player.is_playing();
        dma.queue(0).await;
        if second {
            dma.queue(1).await;
        }
        while dma.active() {
            let free = dma.next_completed().await.expect("active DMA block");
            let commands = take_commands();
            if commands.0.is_some() || commands.1 != player.enabled() {
                dma.drain().await;
                apply(&mut player, commands);
                // Apply newer commands on the next iteration too.
                continue 'playback;
            }
            if ended {
                continue;
            }
            if player.fill_pwm(dma.buffer(free)).is_err() {
                defmt::error!("QOA decode failed");
                dma.buffer(free).fill(SILENCE_WORD);
            }
            ended = !player.is_playing();
            if dma.queue(free).await {
                defmt::warn!("Audio DMA underrun: restarted from silence");
            }
        }
        dma.drain().await;
    }
}
