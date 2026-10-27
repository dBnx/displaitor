//! Optional core-0 timing evidence, readable while halted through SWD.
//!
//! Each screen has 12 u32 words: update, render and swap each have count/sum/max
//! microseconds, followed by loop count/sum/max elapsed microseconds. Sums saturate.
//! Only core 0 writes. Atomic loads/stores avoid shared mutable statics; a debugger
//! must halt core 0 before reading the whole snapshot. Recording is outside the
//! timed regions, but this instrumentation still changes scheduling and code layout.
use core::sync::atomic::{AtomicU32, Ordering};
use displaitor::{AppId, DEFAULT_MENU_COUNT, Screen};

pub const WORDS_PER_SCREEN: usize = 12;
const SCREENS: usize = 1 + DEFAULT_MENU_COUNT + AppId::COUNT;

#[unsafe(no_mangle)]
pub static GAME_TIMINGS: [AtomicU32; SCREENS * WORDS_PER_SCREEN] =
    [const { AtomicU32::new(0) }; SCREENS * WORDS_PER_SCREEN];

// Optional synthetic buttons, consumed through the normal debounce/engine path.
// Bits: A, B, Select, Up, Down, Left, Right. Zero leaves physical inputs alone.
#[unsafe(no_mangle)]
pub static GAME_INPUT: AtomicU32 = AtomicU32::new(0);

// Write a duration in microseconds while halted, then resume without breakpoints.
// Window words are request, actual start, actual finish (wrapping timer low word).
#[unsafe(no_mangle)]
pub static GAME_CAPTURE: [AtomicU32; 3] = [const { AtomicU32::new(0) }; 3];

pub struct Session {
    deadline: Option<u64>,
    first: bool,
}

impl Session {
    pub const fn new() -> Self {
        Self {
            deadline: None,
            first: false,
        }
    }

    pub fn poll(&mut self, now: u64) {
        self.first = false;
        let request = GAME_CAPTURE[0].load(Ordering::Relaxed);
        if request != 0 {
            GAME_CAPTURE[0].store(0, Ordering::Relaxed);
            for word in &GAME_TIMINGS {
                word.store(0, Ordering::Relaxed);
            }
            GAME_CAPTURE[1].store(now as u32, Ordering::Relaxed);
            GAME_CAPTURE[2].store(0, Ordering::Relaxed);
            self.deadline = Some(now + u64::from(request));
            self.first = true;
        }
        if self.deadline.is_some_and(|deadline| now >= deadline) {
            GAME_CAPTURE[2].store(now as u32, Ordering::Relaxed);
            self.deadline = None;
        }
    }

    pub fn record(&self, screen: Screen, stage: usize, micros: u64) {
        // Discard the first iteration: it may catch up after a debugger halt.
        if self.deadline.is_some() && !self.first {
            record(screen, stage, micros);
        }
    }
}

pub fn input() -> displaitor::Controls {
    let mask = GAME_INPUT.load(Ordering::Relaxed);
    displaitor::Controls {
        buttons_a: mask & 1 != 0,
        buttons_b: mask & 2 != 0,
        buttons_s: mask & 4 != 0,
        dpad_up: mask & 8 != 0,
        dpad_down: mask & 16 != 0,
        dpad_left: mask & 32 != 0,
        dpad_right: mask & 64 != 0,
    }
}

fn record(screen: Screen, stage: usize, micros: u64) {
    let screen = match screen {
        Screen::Splash => 0,
        Screen::Menu(id) => 1 + id.index(),
        Screen::App(id) => 1 + DEFAULT_MENU_COUNT + id as usize,
    };
    let offset = screen * WORDS_PER_SCREEN + stage * 3;
    let micros = micros.min(u64::from(u32::MAX)) as u32;
    let count = &GAME_TIMINGS[offset];
    let sum = &GAME_TIMINGS[offset + 1];
    let max = &GAME_TIMINGS[offset + 2];
    count.store(
        count.load(Ordering::Relaxed).saturating_add(1),
        Ordering::Relaxed,
    );
    sum.store(
        sum.load(Ordering::Relaxed).saturating_add(micros),
        Ordering::Relaxed,
    );
    max.store(max.load(Ordering::Relaxed).max(micros), Ordering::Relaxed);
}
