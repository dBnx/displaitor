//! Timestamped input replay and effect coalescing, independent of presentation.
use crate::input::Batch;
use core::time::Duration;
use displaitor::{Controls, Engine, Update};

pub struct Runtime {
    controls: Controls,
    at_us: u64,
    audio_enabled: bool,
}

impl Runtime {
    pub fn new(now_us: u64) -> Self {
        Self {
            controls: Controls::default(),
            at_us: now_us,
            audio_enabled: true,
        }
    }

    pub fn audio_enabled(&self) -> bool {
        self.audio_enabled
    }

    /// Advance with the old held state, then apply each transition at its time.
    /// This preserves short presses and avoids applying new held directions to
    /// the time before they were pressed. Rendering may coalesce all effects.
    pub fn update<const M: usize, const N: usize>(
        &mut self,
        engine: &mut Engine<M>,
        batch: &Batch<N>,
    ) -> Update {
        let mut effects = Update::default();
        for event in batch.transitions() {
            merge(&mut effects, self.advance(engine, event.at_us, true));
            if self.controls.buttons_s && !event.controls.buttons_s {
                self.audio_enabled = !self.audio_enabled;
            }
            self.controls = event.controls;
            merge(
                &mut effects,
                engine.update_local(Duration::ZERO, self.controls),
            );
        }
        merge(&mut effects, self.advance(engine, batch.cutoff_us, false));
        effects
    }

    fn advance<const N: usize>(
        &mut self,
        engine: &mut Engine<N>,
        now_us: u64,
        local_only: bool,
    ) -> Update {
        let elapsed = Duration::from_micros(now_us.saturating_sub(self.at_us));
        self.at_us = self.at_us.max(now_us);
        if local_only {
            engine.update_local(elapsed, self.controls)
        } else {
            engine.update(elapsed, self.controls)
        }
    }
}

fn merge(effects: &mut Update, next: Update) {
    effects.redraw |= next.redraw;
    effects.audio = next.audio.or(effects.audio);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::input::Sampler;
    use displaitor::{AppId, AudioId, Screen};

    #[test]
    fn sampled_pulses_reach_canvas_history_with_timestamps_and_local_effects() {
        use displaitor::canvas_input::ButtonEvent;

        let mut engine = Engine::new();
        let _ = engine.open_canvas();
        let baseline = engine.canvas().buttons(None).latest;
        let mut runtime = Runtime::new(0);
        let mut sampler = Sampler::<32>::new(0);

        // Both debounced edges occur while the foreground is occupied.
        for millis in 1..=30 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    dpad_right: millis <= 15,
                    ..Controls::default()
                },
            );
        }
        let _ = runtime.update(&mut engine, &sampler.drain(30_000));
        let right = engine.canvas().buttons(Some(baseline));
        assert_eq!((right.count, right.flags, right.now_ms), (2, 0, 30));
        assert_eq!(
            &right.events[..2],
            &[
                ButtonEvent {
                    id: baseline + 1,
                    at_ms: 9,
                    state: 0xc0,
                },
                ButtonEvent {
                    id: baseline + 2,
                    at_ms: 24,
                    state: 0x80,
                },
            ]
        );
        assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
        assert!(runtime.audio_enabled());

        for millis in 31..=60 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_s: millis <= 45,
                    ..Controls::default()
                },
            );
        }
        let _ = runtime.update(&mut engine, &sampler.drain(60_000));
        assert!(!runtime.audio_enabled());
        let select = engine.canvas().buttons(Some(right.latest));
        assert_eq!((select.count, select.flags), (2, 0));
        assert_eq!(
            &select.events[..2],
            &[
                ButtonEvent {
                    id: baseline + 3,
                    at_ms: 39,
                    state: 0x84,
                },
                ButtonEvent {
                    id: baseline + 4,
                    at_ms: 54,
                    state: 0x80,
                },
            ]
        );
        let _ = runtime.update(&mut engine, &sampler.drain(61_000));
        assert!(!runtime.audio_enabled());
        assert_eq!(engine.canvas().buttons(Some(select.latest)).count, 0);

        // A queued remote Show must not override the replayed local Back.
        for millis in 62..=91 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_b: millis <= 76,
                    ..Controls::default()
                },
            );
        }
        engine.request_canvas();
        let effects = runtime.update(&mut engine, &sampler.drain(91_000));
        assert!(matches!(engine.screen(), Screen::Menu(_)));
        assert_eq!(effects.audio, Some(AudioId::Stop));
        let back = engine.canvas().buttons(Some(select.latest));
        assert_eq!((back.count, back.flags, back.now_ms), (2, 0, 91));
        assert_eq!(
            &back.events[..2],
            &[
                ButtonEvent {
                    id: baseline + 5,
                    at_ms: 70,
                    state: 0x02,
                },
                ButtonEvent {
                    id: baseline + 6,
                    at_ms: 85,
                    state: 0,
                },
            ]
        );
        assert!(!runtime.audio_enabled());
        assert_eq!(sampler.dropped(), 0);
    }

    #[test]
    fn press_and_release_during_drawing_are_replayed_and_redraw_is_sticky() {
        let mut engine = Engine::new();
        let mut runtime = Runtime::new(0);
        let mut sampler = Sampler::<32>::new(0);
        // Two complete B presses while the main loop is occupied: Splash -> Names -> Home.
        for millis in 1..=60 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_b: millis <= 15 || (31..=45).contains(&millis),
                    ..Controls::default()
                },
            );
        }
        let update = runtime.update(&mut engine, &sampler.drain(60_000));
        assert!(matches!(engine.screen(), Screen::Menu(_)));
        assert!(update.redraw);
        assert_eq!(update.audio, Some(AudioId::Stop));
        assert!(!runtime.update(&mut engine, &sampler.drain(61_000)).redraw);
    }

    #[test]
    fn every_retained_select_release_toggles_once() {
        let mut engine = Engine::new();
        let mut runtime = Runtime::new(0);
        let mut sampler = Sampler::<32>::new(0);
        for millis in 1..=30 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_s: millis <= 15,
                    ..Controls::default()
                },
            );
        }
        let _ = runtime.update(&mut engine, &sampler.drain(30_000));
        assert!(!runtime.audio_enabled());
        for millis in 31..=60 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_s: millis <= 45,
                    ..Controls::default()
                },
            );
        }
        let _ = runtime.update(&mut engine, &sampler.drain(60_000));
        assert!(runtime.audio_enabled());
        let _ = runtime.update(&mut engine, &sampler.drain(61_000));
        assert!(runtime.audio_enabled());
    }

    #[test]
    fn new_input_does_not_apply_to_time_before_its_transition() {
        use displaitor::navigation::{Action, Entry, Menu, MenuId};
        use embedded_graphics::{mock_display::MockDisplay, pixelcolor::Rgb565, prelude::*};
        static MENUS: [Menu<'static>; 1] = [Menu::new(
            "PLAY",
            None,
            &[Entry::new("Pong", Action::App(AppId::Pong))],
        )];
        let mut engine = Engine::with_menus(&MENUS, MenuId::new(0)).unwrap();
        for controls in [
            Controls {
                buttons_b: true,
                ..Controls::default()
            },
            Controls::default(),
            Controls {
                buttons_b: true,
                ..Controls::default()
            },
            Controls::default(),
            Controls {
                buttons_a: true,
                ..Controls::default()
            },
            Controls::default(),
        ] {
            let _ = engine.update(Duration::ZERO, controls);
        }
        assert_eq!(engine.screen(), Screen::App(AppId::Pong));
        let mut runtime = Runtime::new(0);
        let mut sampler = Sampler::<32>::new(0);
        // The Up press is accepted at 998 ms, after almost the entire blocked
        // interval. Applying it to that old interval would move the paddle to y=0.
        for millis in 1..=1_000 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    dpad_up: millis >= 990,
                    ..Controls::default()
                },
            );
        }
        let _ = runtime.update(&mut engine, &sampler.drain(1_000_000));
        let mut display = MockDisplay::new();
        display.set_allow_overdraw(true);
        engine.render(&mut display).unwrap();
        assert_eq!(display.get_pixel(Point::new(0, 0)), Some(Rgb565::BLACK));
        assert_eq!(display.get_pixel(Point::new(0, 11)), Some(Rgb565::CYAN));
    }

    #[test]
    fn local_back_keeps_priority_over_remote_show_during_a_transition_batch() {
        use displaitor::navigation::{Action, Entry, Menu, MenuId};
        static MENUS: [Menu<'static>; 2] = [
            Menu::new(
                "HOME",
                None,
                &[Entry::new("CHILD", Action::Menu(MenuId::new(1)))],
            ),
            Menu::new(
                "CHILD",
                Some(MenuId::new(0)),
                &[Entry::new("Pong", Action::App(AppId::Pong))],
            ),
        ];
        let mut engine = Engine::with_menus(&MENUS, MenuId::new(0)).unwrap();
        for controls in [
            Controls {
                buttons_b: true,
                ..Controls::default()
            },
            Controls::default(),
            Controls {
                buttons_b: true,
                ..Controls::default()
            },
            Controls::default(),
            Controls {
                buttons_a: true,
                ..Controls::default()
            },
            Controls::default(),
        ] {
            let _ = engine.update(Duration::ZERO, controls);
        }
        assert_eq!(engine.screen(), Screen::Menu(MenuId::new(1)));
        let mut sampler = Sampler::<32>::new(0);
        for millis in 1..=20 {
            sampler.sample(
                millis * 1_000,
                Controls {
                    buttons_b: true,
                    ..Controls::default()
                },
            );
        }
        engine.request_canvas();
        let mut runtime = Runtime::new(0);
        let effects = runtime.update(&mut engine, &sampler.drain(20_000));
        assert_eq!(engine.screen(), Screen::Menu(MenuId::new(0)));
        assert!(effects.redraw);
        let _ = runtime.update(&mut engine, &sampler.drain(21_000));
        assert_eq!(engine.screen(), Screen::Menu(MenuId::new(0)));
        // Remote activation still works when no local Back conflicts.
        engine.request_canvas();
        let effects = runtime.update(&mut engine, &sampler.drain(22_000));
        assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
        assert_eq!(effects.audio, Some(AudioId::Stop));
    }
}
