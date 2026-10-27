//! Time-based button debounce, independent of polling speed.
use core::time::Duration;
use displaitor::Controls;

const BUTTONS: usize = 7;
const SETTLE: Duration = Duration::from_millis(8);

/// All fields use `true = pressed`. GPIO adapters invert active-low inputs once.
#[derive(Default)]
pub struct Debouncer {
    stable: [bool; BUTTONS],
    candidate: [bool; BUTTONS],
    age: [Duration; BUTTONS],
}

impl Debouncer {
    pub fn update(&mut self, elapsed: Duration, raw: Controls) -> Controls {
        let values = [
            raw.buttons_a,
            raw.buttons_b,
            raw.buttons_s,
            raw.dpad_up,
            raw.dpad_down,
            raw.dpad_left,
            raw.dpad_right,
        ];
        for (i, value) in values.into_iter().enumerate() {
            if self.candidate[i] != value {
                self.candidate[i] = value;
                // The transition could have happened at any time since the last poll.
                self.age[i] = Duration::ZERO;
            } else {
                self.age[i] = self.age[i].saturating_add(elapsed);
                if self.age[i] >= SETTLE {
                    self.stable[i] = value;
                }
            }
        }
        let [
            buttons_a,
            buttons_b,
            buttons_s,
            dpad_up,
            dpad_down,
            dpad_left,
            dpad_right,
        ] = self.stable;
        Controls {
            buttons_a,
            buttons_b,
            buttons_s,
            dpad_up,
            dpad_down,
            dpad_left,
            dpad_right,
        }
    }
}

/// A debounced transition, timestamped at the sample that accepted it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Transition {
    pub at_us: u64,
    pub controls: Controls,
}

/// A bounded snapshot taken together with its time cutoff by the input adapter.
pub struct Batch<const N: usize> {
    events: [Transition; N],
    len: usize,
    pub cutoff_us: u64,
}

impl<const N: usize> Batch<N> {
    pub fn transitions(&self) -> &[Transition] {
        &self.events[..self.len]
    }
}

/// Retains transitions while the application is drawing or waiting for a buffer.
///
/// Full snapshots preserve press/release ordering, unlike a latest-value mailbox.
/// Overflow drops the oldest transition and counts it; the newest held state is
/// always retained. Capacity must be nonzero. Only the core-0 adapter owns this
/// queue, so it needs local interrupt masking, not a cross-core spinlock.
pub struct Sampler<const N: usize> {
    debounce: Debouncer,
    stable: Controls,
    previous_us: u64,
    events: [Transition; N],
    start: usize,
    len: usize,
    dropped: u32,
}

impl<const N: usize> Sampler<N> {
    pub fn new(now_us: u64) -> Self {
        assert!(N != 0, "input queue needs storage");
        Self {
            debounce: Debouncer::default(),
            stable: Controls::default(),
            previous_us: now_us,
            events: [Transition::default(); N],
            start: 0,
            len: 0,
            dropped: 0,
        }
    }

    pub fn sample(&mut self, now_us: u64, raw: Controls) -> bool {
        let elapsed = Duration::from_micros(now_us.saturating_sub(self.previous_us));
        self.previous_us = now_us;
        let controls = self.debounce.update(elapsed, raw);
        if controls == self.stable {
            return false;
        }
        self.stable = controls;
        if self.len == N {
            self.start = (self.start + 1) % N;
            self.len -= 1;
            self.dropped = self.dropped.saturating_add(1);
        }
        self.events[(self.start + self.len) % N] = Transition {
            at_us: now_us,
            controls,
        };
        self.len += 1;
        true
    }

    pub fn dropped(&self) -> u32 {
        self.dropped
    }

    /// Caller captures `cutoff_us` and drains under the same local IRQ mask.
    pub fn drain(&mut self, cutoff_us: u64) -> Batch<N> {
        let mut batch = Batch {
            events: [Transition::default(); N],
            len: self.len,
            cutoff_us,
        };
        for (index, output) in batch.events.iter_mut().take(self.len).enumerate() {
            *output = self.events[(self.start + index) % N];
        }
        self.start = 0;
        self.len = 0;
        batch
    }
}

/// Absolute 1 ms sampling grid. Late IRQs skip slots rather than invent samples.
pub struct Cadence {
    next_us: u64,
    missed: u32,
}

impl Cadence {
    pub const PERIOD_US: u64 = 1_000;

    pub fn new(now_us: u64) -> Self {
        Self {
            next_us: now_us + Self::PERIOD_US,
            missed: 0,
        }
    }

    pub fn next_us(&self) -> u64 {
        self.next_us
    }

    pub fn sampled(&mut self, now_us: u64) {
        if now_us >= self.next_us {
            let missed = (now_us - self.next_us) / Self::PERIOD_US;
            self.missed = self
                .missed
                .saturating_add(missed.min(u64::from(u32::MAX)) as u32);
            self.next_us += (missed + 1) * Self::PERIOD_US;
        }
    }

    pub fn missed(&self) -> u32 {
        self.missed
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounce_does_not_emit_short_presses() {
        let mut debounce = Debouncer::default();
        let pressed = Controls {
            buttons_s: true,
            ..Controls::default()
        };
        assert!(
            !debounce
                .update(Duration::from_millis(100), pressed)
                .buttons_s
        );
        assert!(!debounce.update(Duration::from_millis(7), pressed).buttons_s);
        assert!(
            !debounce
                .update(Duration::from_millis(1), Controls::default())
                .buttons_s
        );
        debounce.update(Duration::from_millis(1), pressed);
        assert!(debounce.update(Duration::from_millis(8), pressed).buttons_s);
        assert!(
            debounce
                .update(Duration::from_millis(1), Controls::default())
                .buttons_s
        );
        assert!(
            !debounce
                .update(Duration::from_millis(8), Controls::default())
                .buttons_s
        );
    }
    #[test]
    fn independent_buttons_and_long_poll_interval() {
        let mut d = Debouncer::default();
        let mut c = Controls {
            dpad_left: true,
            ..Controls::default()
        };
        d.update(Duration::ZERO, c);
        assert!(d.update(Duration::from_secs(1), c).dpad_left);
        c.buttons_a = true;
        let c = d.update(Duration::from_secs(1), c);
        assert!(c.dpad_left);
        assert!(!c.buttons_a);
    }

    #[test]
    fn transitions_survive_a_whole_press_and_release_between_drains() {
        let mut sampler = Sampler::<4>::new(0);
        let pressed = Controls {
            buttons_a: true,
            ..Controls::default()
        };
        for millis in 1..=30 {
            sampler.sample(
                millis * 1_000,
                if millis <= 15 {
                    pressed
                } else {
                    Controls::default()
                },
            );
        }
        let batch = sampler.drain(30_000);
        assert_eq!(
            batch.transitions(),
            &[
                Transition {
                    at_us: 9_000,
                    controls: pressed
                },
                Transition {
                    at_us: 24_000,
                    controls: Controls::default()
                },
            ]
        );
        assert!(sampler.drain(31_000).transitions().is_empty());
        assert_eq!(sampler.dropped(), 0);
    }

    #[test]
    fn overflow_retains_ordered_latest_states_and_counts_drops() {
        let mut sampler = Sampler::<2>::new(0);
        for millis in 1..=60 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_s: (millis - 1) / 10 % 2 == 0,
                    ..Controls::default()
                },
            );
        }
        let batch = sampler.drain(60_000);
        assert_eq!(batch.transitions().len(), 2);
        assert_eq!(batch.transitions()[0].at_us, 49_000);
        assert!(batch.transitions()[0].controls.buttons_s);
        assert_eq!(batch.transitions()[1].at_us, 59_000);
        assert!(!batch.transitions()[1].controls.buttons_s);
        assert_eq!(sampler.dropped(), 4);
    }

    #[test]
    fn delayed_sampling_skips_slots_and_keeps_the_original_grid() {
        let mut cadence = Cadence::new(123);
        assert_eq!(cadence.next_us(), 1_123);
        cadence.sampled(1_200);
        assert_eq!(cadence.next_us(), 2_123);
        cadence.sampled(5_500);
        assert_eq!(cadence.next_us(), 6_123);
        assert_eq!(cadence.missed(), 3);
    }
}
