//! Bounded, non-destructive button history shared by all Canvas transports.
use core::time::Duration;

use crate::Controls;

pub const HISTORY_CAPACITY: usize = 32;
pub const MAX_EVENTS: usize = 4;
pub const FLAG_MORE: u8 = 0x01;
pub const FLAG_LOST: u8 = 0x02;
pub const CANVAS_ACTIVE: u8 = 0x80;

/// State bits 0..6 are A, B, Select, Up, Down, Left, Right; bit 7 is Canvas active.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ButtonEvent {
    pub id: u32,
    pub at_ms: u32,
    pub state: u8,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ButtonsReport {
    pub state: u8,
    pub flags: u8,
    pub latest: u32,
    pub overwritten: u32,
    pub now_ms: u32,
    pub count: u8,
    pub events: [ButtonEvent; MAX_EVENTS],
}

pub(crate) struct ButtonHistory {
    events: [ButtonEvent; HISTORY_CAPACITY],
    next: usize,
    len: usize,
    latest: u32,
    overwritten: u32,
    clock_us: u64,
    state: u8,
}

impl ButtonHistory {
    pub const fn new() -> Self {
        Self {
            events: [ButtonEvent {
                id: 0,
                at_ms: 0,
                state: 0,
            }; HISTORY_CAPACITY],
            next: 0,
            len: 0,
            latest: 0,
            overwritten: 0,
            clock_us: 0,
            state: 0,
        }
    }

    pub fn record(&mut self, elapsed: Duration, controls: Controls, active: bool) {
        self.clock_us = self
            .clock_us
            .saturating_add(elapsed.as_micros().min(u128::from(u64::MAX)) as u64);
        let state = u8::from(controls.buttons_a)
            | (u8::from(controls.buttons_b) << 1)
            | (u8::from(controls.buttons_s) << 2)
            | (u8::from(controls.dpad_up) << 3)
            | (u8::from(controls.dpad_down) << 4)
            | (u8::from(controls.dpad_left) << 5)
            | (u8::from(controls.dpad_right) << 6)
            | if active { CANVAS_ACTIVE } else { 0 };
        if state == self.state {
            return;
        }
        self.state = state;
        self.latest = self.latest.wrapping_add(1);
        self.events[self.next] = ButtonEvent {
            id: self.latest,
            at_ms: self.now_ms(),
            state,
        };
        self.next = (self.next + 1) % HISTORY_CAPACITY;
        if self.len == HISTORY_CAPACITY {
            self.overwritten = self.overwritten.saturating_add(1);
        } else {
            self.len += 1;
        }
    }

    fn now_ms(&self) -> u32 {
        (self.clock_us / 1_000) as u32
    }

    /// `None` establishes a baseline. Reading never consumes or acknowledges events.
    pub fn read(&self, after_id: Option<u32>) -> ButtonsReport {
        let mut report = ButtonsReport {
            state: self.state,
            latest: self.latest,
            overwritten: self.overwritten,
            now_ms: self.now_ms(),
            ..ButtonsReport::default()
        };
        let Some(after_id) = after_id else {
            return report;
        };
        let available = self.latest.wrapping_sub(after_id);
        // Half-range comparison rejects future/ambiguous cursors across sequence wrap.
        if available >= 0x8000_0000 || available > self.len as u32 {
            report.flags = FLAG_LOST;
            return report;
        }
        let available = available as usize;
        let count = available.min(MAX_EVENTS);
        let start = (self.next + HISTORY_CAPACITY - available) % HISTORY_CAPACITY;
        for index in 0..count {
            report.events[index] = self.events[(start + index) % HISTORY_CAPACITY];
        }
        report.count = count as u8;
        if available > count {
            report.flags = FLAG_MORE;
        }
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sequence_and_millisecond_wrap_keep_order_and_fractional_time() {
        let mut history = ButtonHistory::new();
        history.latest = u32::MAX - 1;
        history.clock_us = u64::from(u32::MAX) * 1_000 + 500;
        history.record(Duration::from_micros(499), Controls::default(), true);
        history.record(Duration::from_micros(1), Controls::default(), false);
        let report = history.read(Some(u32::MAX - 1));
        assert_eq!(report.count, 2);
        assert_eq!(
            report.events[0],
            ButtonEvent {
                id: u32::MAX,
                at_ms: u32::MAX,
                state: CANVAS_ACTIVE
            }
        );
        assert_eq!(
            report.events[1],
            ButtonEvent {
                id: 0,
                at_ms: 0,
                state: 0
            }
        );
        assert_eq!(report.now_ms, 0);
        assert_eq!(report.flags, 0);
        assert_eq!(history.read(Some(1)).flags, FLAG_LOST);
        assert_eq!(history.read(Some(0x8000_0000)).flags, FLAG_LOST);
    }

    #[test]
    fn overwritten_counter_saturates() {
        let mut history = ButtonHistory::new();
        for index in 0..HISTORY_CAPACITY {
            history.record(Duration::ZERO, Controls::default(), index % 2 == 0);
        }
        history.overwritten = u32::MAX;
        history.record(Duration::ZERO, Controls::default(), true);
        assert_eq!(history.read(None).overwritten, u32::MAX);
    }
}
