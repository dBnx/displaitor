//! Owned playback and sample-rate conversion shared by both adapters.
use displaitor::AudioId;
use qoa_decoder::{QoaDecoder, QoaError};

pub struct Player {
    decoder: Option<QoaDecoder<'static>>,
    enabled: bool,
    repeat: bool,
}

impl Default for Player {
    fn default() -> Self {
        Self {
            decoder: None,
            enabled: true,
            repeat: false,
        }
    }
}

impl Player {
    /// Starts from the beginning, including repeated requests for the same clip.
    /// IDs without an asset behave as Stop. A malformed asset stops playback.
    pub fn select(&mut self, id: AudioId) -> Result<(), QoaError> {
        self.decoder = None;
        self.repeat = matches!(
            id,
            AudioId::MusicTetris | AudioId::MusicPPAP | AudioId::MusicPen | AudioId::MusicNyan
        );
        if let Some(data) = id.file() {
            self.decoder = Some(QoaDecoder::new(data)?);
        }
        Ok(())
    }
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }
    pub fn enabled(&self) -> bool {
        self.enabled
    }
    pub fn sample_rate(&self) -> Option<u32> {
        self.decoder.as_ref().map(QoaDecoder::sample_rate)
    }
    /// Muting pauses decoding. Music loops; effects stop at EOF. Errors stop playback.
    pub fn next_sample(&mut self) -> Result<Option<i16>, QoaError> {
        if !self.enabled {
            return Ok(None);
        }
        let result = match self.decoder.as_mut() {
            Some(decoder) => match decoder.try_next_sample() {
                Ok(None) if self.repeat => {
                    decoder.reset();
                    decoder.try_next_sample()
                }
                result => result,
            },
            None => return Ok(None),
        };
        if !matches!(result, Ok(Some(_))) {
            self.decoder = None;
        }
        result
    }
}

/// Firmware output is paced by DMA, independently of decoding and PWM carrier timing.
pub const OUTPUT_RATE: u32 = 32_000;
pub const BLOCK_SAMPLES: usize = 64;
pub const SILENCE_WORD: u32 = 127 << 16;

/// Latest selection and mute state, coalesced between audio blocks. Repeated
/// state-only updates do not wake an idle decoder; repeated clip requests do.
pub struct CommandMailbox {
    clip: Option<AudioId>,
    enabled: bool,
}

impl CommandMailbox {
    pub const fn new() -> Self {
        Self {
            clip: None,
            enabled: true,
        }
    }

    pub fn request(&mut self, clip: Option<AudioId>, enabled: bool) -> bool {
        let changed = clip.is_some() || enabled != self.enabled;
        if clip.is_some() {
            self.clip = clip;
        }
        self.enabled = enabled;
        changed
    }

    pub fn take(&mut self) -> (Option<AudioId>, bool) {
        (self.clip.take(), self.enabled)
    }
}

impl Default for CommandMailbox {
    fn default() -> Self {
        Self::new()
    }
}

/// Decide recovery only after the successor has been disabled. TRANS_COUNT
/// writes set RELOAD; an untouched channel and a finished channel both read zero
/// in the live counter. A completion event distinguishes those two idle states.
pub fn successor_needs_fresh_start(busy: bool, completion_seen: bool) -> bool {
    !busy && !completion_seen
}

/// Neither live count zero nor !BUSY proves that a prepared channel ever ran.
/// Require its completion event as well, retaining in-flight writes until idle.
pub fn dma_transfer_completed(busy: bool, remaining: u32, completion_seen: bool) -> bool {
    completion_seen && !busy && remaining == 0
}

/// Sample-and-hold rate conversion. Muting preserves both decoder and fractional phase.
/// This also supports the retained 100 Hz Nyan asset without a very slow DMA clock.
pub struct OutputPlayer {
    player: Player,
    output_rate: u32,
    phase: u32,
    sample: i16,
}
impl OutputPlayer {
    pub fn new(output_rate: u32) -> Self {
        assert!((1..=1_000_000).contains(&output_rate));
        Self {
            player: Player::default(),
            output_rate,
            phase: output_rate,
            sample: 0,
        }
    }
    pub fn select(&mut self, id: AudioId) -> Result<(), QoaError> {
        self.phase = self.output_rate;
        self.sample = 0;
        self.player.select(id)
    }
    pub fn set_enabled(&mut self, enabled: bool) {
        self.player.set_enabled(enabled);
    }
    pub fn enabled(&self) -> bool {
        self.player.enabled()
    }
    pub fn is_playing(&self) -> bool {
        self.enabled() && self.player.sample_rate().is_some()
    }
    pub fn next_sample(&mut self) -> Result<Option<i16>, QoaError> {
        if !self.enabled() {
            return Ok(None);
        }
        let Some(rate) = self.player.sample_rate() else {
            return Ok(None);
        };
        while self.phase >= self.output_rate {
            self.phase -= self.output_rate;
            match self.player.next_sample() {
                Ok(Some(sample)) => self.sample = sample,
                result => {
                    self.sample = 0;
                    return result;
                }
            }
        }
        let sample = self.sample;
        self.phase += rate;
        Ok(Some(sample))
    }
    /// Fill a complete PWM5 CC block, padding EOF with midpoint silence.
    /// Returns whether the block contains any source samples, including zero samples.
    pub fn fill_pwm(&mut self, output: &mut [u32]) -> Result<bool, QoaError> {
        output.fill(SILENCE_WORD);
        let mut has_audio = false;
        for word in output {
            let Some(sample) = self.next_sample()? else {
                break;
            };
            *word = u32::from(sample_to_duty(sample)) << 16;
            has_audio = true;
        }
        Ok(has_audio)
    }
}

/// PWM TOP=255: silence is the midpoint, rather than a rail.
pub fn sample_to_duty(sample: i16) -> u16 {
    ((i32::from(sample) + 32768) as u32 * 255 / 65535) as u16
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pwm_covers_both_rails_and_midpoint() {
        assert_eq!(sample_to_duty(i16::MIN), 0);
        assert_eq!(sample_to_duty(i16::MAX), 255);
        assert_eq!(sample_to_duty(0), 127);
    }
    #[test]
    fn background_music_loops_seamlessly_and_stop_cancels_it() {
        let mut p = Player::default();
        p.select(AudioId::MusicNyan).unwrap();
        let bytes = AudioId::MusicNyan.file().unwrap();
        let length = u32::from_be_bytes(bytes[4..8].try_into().unwrap());
        let first = p.next_sample().unwrap();
        assert!(first.is_some());
        for _ in 1..length {
            assert!(p.next_sample().unwrap().is_some());
        }
        assert_eq!(p.next_sample().unwrap(), first);
        assert!(p.sample_rate().is_some());
        p.select(AudioId::Stop).unwrap();
        assert_eq!(p.next_sample().unwrap(), None);
    }
    #[test]
    fn playback_mute_restart_stop_and_eof() {
        let mut p = Player::default();
        p.select(AudioId::Ping).unwrap();
        let first = p.next_sample().unwrap();
        assert!(first.is_some());
        p.set_enabled(false);
        assert_eq!(p.next_sample().unwrap(), None);
        assert!(p.sample_rate().is_some());
        p.set_enabled(true);
        assert!(p.next_sample().unwrap().is_some());
        p.select(AudioId::Ping).unwrap();
        assert_eq!(p.next_sample().unwrap(), first);
        let mut count = 1;
        while p.next_sample().unwrap().is_some() {
            count += 1;
            assert!(count < 1_000_000);
        }
        assert_eq!(p.sample_rate(), None);
        p.select(AudioId::Stop).unwrap();
        assert_eq!(p.next_sample().unwrap(), None);
    }
    #[test]
    fn resampling_tracks_source_time_across_asset_rates() {
        for id in [
            AudioId::Ping,
            AudioId::MusicTetris,
            AudioId::MusicPPAP,
            AudioId::MusicNyan,
        ] {
            let mut source = Player::default();
            source.select(id).unwrap();
            let rate = u64::from(source.sample_rate().unwrap());
            let mut output = OutputPlayer::new(OUTPUT_RATE);
            output.select(id).unwrap();
            let mut source_index = 0;
            let mut expected = source.next_sample().unwrap();
            for index in 0..10_000_u64 {
                let required = index * rate / u64::from(OUTPUT_RATE);
                while source_index < required {
                    expected = source.next_sample().unwrap();
                    source_index += 1;
                }
                assert_eq!(
                    output.next_sample().unwrap(),
                    expected,
                    "{id:?} output {index}"
                );
            }
        }
    }
    #[test]
    fn muted_blocks_preserve_fractional_pause_position() {
        let mut expected = OutputPlayer::new(OUTPUT_RATE);
        let mut paused = OutputPlayer::new(OUTPUT_RATE);
        expected.select(AudioId::MusicTetris).unwrap();
        paused.select(AudioId::MusicTetris).unwrap();
        for _ in 0..91 {
            assert_eq!(
                expected.next_sample().unwrap(),
                paused.next_sample().unwrap()
            );
        }
        paused.set_enabled(false);
        let mut block = [0; BLOCK_SAMPLES];
        for _ in 0..10 {
            assert!(!paused.fill_pwm(&mut block).unwrap());
            assert_eq!(block, [SILENCE_WORD; BLOCK_SAMPLES]);
        }
        paused.set_enabled(true);
        for _ in 0..1_000 {
            assert_eq!(
                expected.next_sample().unwrap(),
                paused.next_sample().unwrap()
            );
        }
    }
    #[test]
    fn effect_eof_and_stop_produce_complete_silent_blocks() {
        let mut output = OutputPlayer::new(OUTPUT_RATE);
        output.select(AudioId::Ping).unwrap();
        let samples = u32::from_be_bytes(AudioId::Ping.file().unwrap()[4..8].try_into().unwrap());
        let mut block = [0; BLOCK_SAMPLES];
        for _ in 0..samples as usize / BLOCK_SAMPLES {
            assert!(output.fill_pwm(&mut block).unwrap());
            assert!(
                block
                    .iter()
                    .all(|word| word & 0xffff == 0 && word >> 16 <= 255)
            );
        }
        assert!(!output.fill_pwm(&mut block).unwrap());
        assert_eq!(block, [SILENCE_WORD; BLOCK_SAMPLES]);
        output.select(AudioId::MusicNyan).unwrap();
        assert!(output.fill_pwm(&mut block).unwrap());
        output.select(AudioId::Stop).unwrap();
        assert!(!output.fill_pwm(&mut block).unwrap());
        assert_eq!(block, [SILENCE_WORD; BLOCK_SAMPLES]);
    }
    #[test]
    fn resampled_music_loops_without_a_silent_gap() {
        let mut output = OutputPlayer::new(100);
        output.select(AudioId::MusicNyan).unwrap();
        let first = output.next_sample().unwrap();
        let length =
            u32::from_be_bytes(AudioId::MusicNyan.file().unwrap()[4..8].try_into().unwrap());
        for _ in 1..length {
            assert!(output.next_sample().unwrap().is_some());
        }
        assert_eq!(output.next_sample().unwrap(), first);
        assert!(output.is_playing());
    }
    #[test]
    fn fractional_effect_eof_pads_the_last_partial_block() {
        let mut output = OutputPlayer::new(44_100);
        output.select(AudioId::Ping).unwrap();
        let bytes = AudioId::Ping.file().unwrap();
        let source_samples = u32::from_be_bytes(bytes[4..8].try_into().unwrap());
        let source_rate = u32::from_be_bytes([0, bytes[9], bytes[10], bytes[11]]);
        let output_samples = (u64::from(source_samples) * 44_100).div_ceil(u64::from(source_rate));
        let mut block = [0; BLOCK_SAMPLES];
        for _ in 0..output_samples as usize / BLOCK_SAMPLES {
            assert!(output.fill_pwm(&mut block).unwrap());
        }
        assert!(output.fill_pwm(&mut block).unwrap());
        let tail = output_samples as usize % BLOCK_SAMPLES;
        assert_ne!(tail, 0);
        assert!(block[tail..].iter().all(|word| *word == SILENCE_WORD));
        assert!(!output.fill_pwm(&mut block).unwrap());
        assert_eq!(block, [SILENCE_WORD; BLOCK_SAMPLES]);
    }
    /// RP2040 TRANS_COUNT has distinct write-RELOAD/read-LIVE semantics.
    /// Fixture follows the register contract rather than treating a write as
    /// changing the live count (the assumption that hid the hardware failure).
    #[derive(Default)]
    struct DmaRegisters {
        reload: u32,
        live: u32,
        busy: bool,
        completion: bool,
        transferred: u32,
        triggers: u32,
    }
    impl DmaRegisters {
        fn prepare(&mut self, count: u32) {
            assert!(!self.busy);
            self.completion = false;
            self.reload = count; // Writing TRANS_COUNT does not change LIVE.
        }
        fn trigger(&mut self) {
            if !self.busy {
                self.live = self.reload;
                self.busy = true;
                self.triggers += 1;
            }
        }
        fn transfer(&mut self, count: u32) {
            assert!(self.busy && count <= self.live);
            self.live -= count;
            self.transferred += count;
        }
        fn retire(&mut self) {
            assert!(self.busy && self.live == 0);
            self.busy = false;
            self.completion = true;
        }
        fn completed(&self) -> bool {
            dma_transfer_completed(self.busy, self.live, self.completion)
        }
        fn needs_start(&self) -> bool {
            successor_needs_fresh_start(self.busy, self.completion)
        }
    }

    #[test]
    fn programmed_reload_needs_a_trigger_and_cannot_be_reclaimed_as_completed() {
        let mut channel = DmaRegisters::default();
        for expected_total in [64, 128] {
            channel.prepare(BLOCK_SAMPLES as u32);
            assert_eq!(channel.reload, 64);
            assert_eq!(channel.live, 0);
            assert!(!channel.completed());
            assert!(channel.needs_start());
            channel.trigger();
            assert!(!channel.needs_start());
            channel.transfer(64);
            assert!(!channel.completed()); // Last write has not retired.
            channel.retire();
            assert!(channel.completed());
            assert!(!channel.needs_start()); // Never replay a completed block.
            assert_eq!(channel.transferred, expected_total);
        }
        assert_eq!(channel.triggers, 2);
    }

    #[test]
    fn late_handoff_preserves_every_sample_without_replaying_started_successors() {
        // A CPU pause can end before the successor starts, during it, or after
        // it completes. The register LIVE value is zero in TWO of those cases.
        for progress in [0, 17, 64] {
            let mut successor = DmaRegisters::default();
            successor.prepare(64);
            if progress != 0 {
                successor.trigger();
                successor.transfer(progress);
                if progress == 64 {
                    successor.retire();
                }
            }
            if successor.needs_start() {
                successor.trigger();
            }
            if successor.busy {
                successor.transfer(successor.live);
                successor.retire();
            }
            assert!(successor.completed());
            assert_eq!(successor.transferred, 64);
            assert_eq!(successor.triggers, 1);
        }
    }

    #[test]
    fn fallback_wait_retains_untriggered_reload_and_the_final_sample_hold() {
        let mut fallback = DmaRegisters::default();
        fallback.prepare(1);
        assert_eq!(fallback.live, 0);
        assert!(!fallback.completed()); // A pending chain has not run.
        fallback.trigger();
        assert!(!fallback.completed()); // Wait until the next 32 kHz sample tick.
        fallback.transfer(1);
        assert!(!fallback.completed()); // Preserve its in-flight write too.
        fallback.retire();
        assert!(fallback.completed());
        fallback.prepare(1);
        assert_eq!(fallback.live, 0);
        assert!(!fallback.completed()); // Previous completion cannot release it.
    }

    #[test]
    fn idle_mailbox_wakes_only_for_changes_and_preserves_pending_clip() {
        let mut commands = CommandMailbox::new();
        for _ in 0..1000 {
            assert!(!commands.request(None, true));
        }
        assert!(commands.request(Some(AudioId::Ping), true));
        assert!(!commands.request(None, true));
        assert!(commands.request(None, false));
        assert_eq!(commands.take(), (Some(AudioId::Ping), false));
        assert_eq!(commands.take(), (None, false));
        assert!(!commands.request(None, false));
        assert!(commands.request(None, true));
    }

    #[test]
    fn latest_selection_wins_and_repeated_selection_still_restarts() {
        let mut commands = CommandMailbox::new();
        assert!(commands.request(Some(AudioId::Ping), true));
        assert!(commands.request(Some(AudioId::Stop), true));
        assert_eq!(commands.take(), (Some(AudioId::Stop), true));
        assert!(commands.request(Some(AudioId::Stop), true));
        assert_eq!(commands.take(), (Some(AudioId::Stop), true));
    }
}
