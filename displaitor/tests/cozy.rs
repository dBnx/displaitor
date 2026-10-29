use core::{convert::Infallible, time::Duration};
use displaitor::{AppId, AudioId, Controls, Engine, Screen, navigation::MenuId};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

#[derive(Debug, PartialEq, Eq)]
struct Frame([Rgb565; 2048]);

impl OriginDimensions for Frame {
    fn size(&self) -> Size {
        Size::new(64, 32)
    }
}
impl DrawTarget for Frame {
    type Color = Rgb565;
    type Error = Infallible;
    fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
        &mut self,
        pixels: I,
    ) -> Result<(), Self::Error> {
        for Pixel(point, color) in pixels {
            assert!((0..64).contains(&point.x) && (0..32).contains(&point.y));
            self.0[point.y as usize * 64 + point.x as usize] = color;
        }
        Ok(())
    }
}
fn frame(engine: &Engine) -> Frame {
    let mut target = Frame([Rgb565::BLACK; 2048]);
    engine.render(&mut target).unwrap();
    target
}
fn tap(engine: &mut Engine, controls: Controls) -> displaitor::Update {
    let _ = engine.update(Duration::ZERO, Controls::default());
    let update = engine.update(Duration::ZERO, controls);
    let _ = engine.update(Duration::ZERO, Controls::default());
    update
}
fn select() -> Controls {
    Controls {
        buttons_a: true,
        ..Controls::default()
    }
}
fn back() -> Controls {
    Controls {
        buttons_b: true,
        ..Controls::default()
    }
}

const SCENES: [AppId; 10] = [
    AppId::CozyFarm,
    AppId::CozyWinter,
    AppId::CozyOkami,
    AppId::CozyWitcher,
    AppId::CozyReef,
    AppId::Fire,
    AppId::CozyPalico,
    AppId::CozyRathalos,
    AppId::CozyZinogre,
    AppId::CozyPoogie,
];

#[test]
fn watch_launches_every_scene_and_back_keeps_its_origin() {
    let mut engine = Engine::new();
    let _ = tap(&mut engine, back());
    let _ = tap(&mut engine, back());
    let _ = tap(
        &mut engine,
        Controls {
            dpad_down: true,
            ..Controls::default()
        },
    );
    let _ = tap(&mut engine, select());
    assert_eq!(engine.navigation().current_menu().title, "WATCH");
    for (index, app) in [
        AppId::Nyan,
        AppId::Hyper,
        AppId::Fire,
        AppId::CozyFarm,
        AppId::CozyWinter,
        AppId::CozyOkami,
        AppId::CozyWitcher,
        AppId::CozyReef,
        AppId::CozyPalico,
        AppId::CozyRathalos,
        AppId::CozyZinogre,
        AppId::CozyPoogie,
    ]
    .into_iter()
    .enumerate()
    {
        let update = tap(&mut engine, select());
        if SCENES.contains(&app) {
            assert_eq!(update.audio, Some(AudioId::Stop));
        }
        assert_eq!(engine.screen(), Screen::App(app));
        let _ = tap(&mut engine, back());
        assert_eq!(engine.screen(), Screen::Menu(MenuId::new(1)));
        assert_eq!(engine.selected_entry(), index);
        let _ = tap(
            &mut engine,
            Controls {
                dpad_down: true,
                ..Controls::default()
            },
        );
    }
    let _ = tap(&mut engine, back());
    assert_eq!(engine.screen(), Screen::Menu(MenuId::new(0)));
    assert_eq!(engine.selected_entry(), 1);
}

#[test]
fn every_scene_cycles_both_directions_and_wraps_while_paused() {
    let mut engine = Engine::new();
    let _ = engine.open_app(SCENES[0]);
    let _ = tap(&mut engine, pause());
    for forward in [true, false] {
        for step in 1..=SCENES.len() {
            let _ = tap(
                &mut engine,
                Controls {
                    dpad_right: forward,
                    dpad_left: !forward,
                    ..Controls::default()
                },
            );
            let expected = if forward {
                step % SCENES.len()
            } else {
                (SCENES.len() - step) % SCENES.len()
            };
            assert_eq!(engine.screen(), Screen::App(SCENES[expected]));
            assert_eq!(engine.next_update_after(), None);
            let _ = frame(&engine);
        }
    }
}

#[test]
fn scenes_run_without_canvas_and_retain_fractional_deadlines_across_stalls() {
    for app in SCENES {
        let mut whole = Engine::new();
        let mut split = Engine::new();
        let _ = whole.open_app(app);
        let _ = split.open_app(app);
        let initial = frame(&whole);
        assert!(
            initial
                .0
                .chunks(64)
                .any(|row| row[40..].iter().any(|&c| c != Rgb565::BLACK))
        );
        let _ = whole.update(Duration::from_millis(525), Controls::default());
        for _ in 0..21 {
            let _ = split.update(Duration::from_millis(25), Controls::default());
        }
        assert_eq!(frame(&whole), frame(&split));
        assert_ne!(initial, frame(&whole));
        assert_eq!(whole.next_update_after(), Some(Duration::from_millis(75)));
        let loop_time = if app == AppId::CozyWinter { 32 } else { 16 };
        let before = frame(&whole);
        let _ = whole.update(Duration::from_secs(loop_time), Controls::default());
        assert_eq!(frame(&whole), before);
        assert_eq!(whole.next_update_after(), Some(Duration::from_millis(75)));
        let effects = whole.update(Duration::MAX, Controls::default());
        assert_eq!(effects.audio, None);
        assert!(whole.next_update_after().unwrap() <= Duration::from_millis(100));
        let _ = frame(&whole);
    }
}

#[test]
fn paused_scenes_sleep_and_resume_without_counting_time_spent_paused() {
    let mut engine = Engine::new();
    let _ = engine.open_app(AppId::CozyWinter);
    let _ = engine.update(Duration::from_millis(25), Controls::default());
    let _ = engine.update(Duration::from_millis(25), pause());
    assert_eq!(engine.next_update_after(), None);
    let paused = frame(&engine);
    assert!(!engine.update(Duration::MAX, Controls::default()).redraw);
    assert_eq!(frame(&engine), paused);
    assert_eq!(engine.next_update_after(), None);
    let _ = tap(&mut engine, resume());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(50)));
    assert_eq!(frame(&engine), paused);
    let _ = engine.update(Duration::from_millis(50), Controls::default());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(100)));
    assert_ne!(frame(&engine), paused);
}

#[test]
fn switching_keeps_pause_and_local_back_wins_over_scene_controls() {
    let mut engine = Engine::new();
    let _ = engine.open_app(AppId::CozyFarm);
    let _ = tap(&mut engine, pause());
    let _ = tap(
        &mut engine,
        Controls {
            dpad_right: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), Screen::App(AppId::CozyWinter));
    assert_eq!(engine.next_update_after(), None);
    let _ = tap(
        &mut engine,
        Controls {
            dpad_left: true,
            dpad_right: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), Screen::App(AppId::CozyWinter));
    let _ = tap(
        &mut engine,
        Controls {
            dpad_left: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), Screen::App(AppId::CozyFarm));
    let _ = tap(
        &mut engine,
        Controls {
            buttons_b: true,
            buttons_a: true,
            dpad_right: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), Screen::Menu(MenuId::new(0)));
    assert_eq!(engine.next_update_after(), None);
    let _ = engine.open_app(AppId::CozyFarm);
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(100)));
}

fn pause() -> Controls {
    Controls {
        dpad_up: true,
        ..Controls::default()
    }
}
fn resume() -> Controls {
    Controls {
        dpad_down: true,
        ..Controls::default()
    }
}

#[test]
fn actions_finish_retrigger_and_cancel_without_displacing_the_background() {
    for app in SCENES {
        let mut engine = Engine::new();
        let _ = engine.open_app(app);
        let _ = engine.update(Duration::from_millis(1500), Controls::default());
        let _ = tap(&mut engine, pause());
        let ambient = frame(&engine);
        assert!(tap(&mut engine, select()).redraw);
        assert_eq!(engine.next_update_after(), Some(Duration::from_millis(100)));
        let _ = engine.update(Duration::from_millis(725), Controls::default());
        assert_ne!(frame(&engine), ambient, "{app:?}");
        assert_eq!(engine.next_update_after(), Some(Duration::from_millis(75)));
        let _ = tap(&mut engine, select());
        assert_eq!(engine.next_update_after(), Some(Duration::from_millis(100)));
        assert!(
            engine
                .update(Duration::from_millis(3200), Controls::default())
                .redraw
        );
        assert_eq!(frame(&engine), ambient, "{app:?}");
        assert_eq!(engine.next_update_after(), None);
        let _ = tap(&mut engine, select());
        let _ = tap(
            &mut engine,
            Controls {
                dpad_right: true,
                ..Controls::default()
            },
        );
        assert_eq!(engine.next_update_after(), None);
        let _ = tap(&mut engine, resume());
        assert!(engine.next_update_after().is_some());
    }
}

#[test]
fn ambient_and_action_clocks_handle_split_and_huge_elapsed_times() {
    for app in SCENES {
        let mut whole = Engine::new();
        let mut split = Engine::new();
        for engine in [&mut whole, &mut split] {
            let _ = engine.open_app(app);
            let _ = engine.update(Duration::from_millis(25), Controls::default());
            let _ = tap(engine, select());
        }
        let _ = whole.update(Duration::from_millis(725), Controls::default());
        for _ in 0..29 {
            let _ = split.update(Duration::from_millis(25), Controls::default());
        }
        assert_eq!(frame(&whole), frame(&split));
        assert_eq!(whole.next_update_after(), Some(Duration::from_millis(50)));
        assert_eq!(whole.next_update_after(), split.next_update_after());
        let _ = whole.update(Duration::MAX, Controls::default());
        let _ = frame(&whole);
        assert!(whole.next_update_after().unwrap() <= Duration::from_millis(100));
    }
}

#[test]
fn original_watch_movies_have_temporary_actions_too() {
    for app in [AppId::Nyan, AppId::Hyper] {
        let mut effect = Engine::new();
        let mut ambient = Engine::new();
        let _ = effect.open_app(app);
        let _ = ambient.open_app(app);
        let _ = tap(&mut effect, select());
        assert_ne!(frame(&effect), frame(&ambient));
        for elapsed in [Duration::from_millis(725), Duration::from_millis(2475)] {
            let _ = effect.update(elapsed, Controls::default());
            let _ = ambient.update(elapsed, Controls::default());
        }
        assert_eq!(frame(&effect), frame(&ambient));
        assert_eq!(effect.next_update_after(), ambient.next_update_after());
    }
}

#[test]
fn nyan_decoder_keeps_restored_source_midtones_until_the_output_boundary() {
    let mut engine = Engine::new();
    let _ = engine.open_app(AppId::Nyan);
    let rendered = frame(&engine);
    // First-frame source pixels: grey #999999 and sky #003366, quantized
    // directly to RGB565. The hardware output applies gamma afterwards.
    assert_eq!(
        rendered
            .0
            .iter()
            .filter(|pixel| **pixel == Rgb565::new(19, 38, 19))
            .count(),
        114
    );
    assert!(rendered.0.contains(&Rgb565::new(0, 13, 12)));
}
