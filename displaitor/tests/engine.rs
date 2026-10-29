use core::{convert::Infallible, time::Duration};
use displaitor::{AppId, AudioId, Controls, Engine, HEIGHT, Screen, WIDTH, navigation::MenuId};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

const ROOT: MenuId = MenuId::new(0);
const WATCH: MenuId = MenuId::new(1);
const PLAY: MenuId = MenuId::new(2);

#[derive(Clone, Debug, PartialEq)]
struct Frame([Rgb565; (WIDTH * HEIGHT) as usize]);

impl Default for Frame {
    fn default() -> Self {
        Self([Rgb565::BLACK; (WIDTH * HEIGHT) as usize])
    }
}

impl OriginDimensions for Frame {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}

impl DrawTarget for Frame {
    type Color = Rgb565;
    type Error = Infallible;
    fn draw_iter<I>(&mut self, pixels: I) -> Result<(), Self::Error>
    where
        I: IntoIterator<Item = Pixel<Self::Color>>,
    {
        for Pixel(point, color) in pixels {
            assert!((0..WIDTH as i32).contains(&point.x), "x={}", point.x);
            assert!((0..HEIGHT as i32).contains(&point.y), "y={}", point.y);
            self.0[point.y as usize * WIDTH as usize + point.x as usize] = color;
        }
        Ok(())
    }
}

fn frame(engine: &Engine) -> Frame {
    let mut display = Frame::default();
    engine.render(&mut display).unwrap();
    display
}

fn tap(engine: &mut Engine, control: Controls) -> displaitor::Update {
    let _ = engine.update(Duration::ZERO, Controls::default());
    let update = engine.update(Duration::ZERO, control);
    let _ = engine.update(Duration::ZERO, Controls::default());
    update
}

fn back(engine: &mut Engine) {
    let _ = tap(
        engine,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
}
fn down(engine: &mut Engine) {
    let _ = tap(
        engine,
        Controls {
            dpad_down: true,
            ..Controls::default()
        },
    );
}
fn enter(engine: &mut Engine) -> displaitor::Update {
    tap(
        engine,
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    )
}
fn main_menu(engine: &mut Engine) {
    back(engine);
    back(engine);
    assert_eq!(engine.screen(), Screen::Menu(ROOT));
}

#[test]
fn splash_uses_elapsed_time_and_redraws_only_on_frame_changes() {
    let mut engine = Engine::new();
    assert!(engine.update(Duration::ZERO, Controls::default()).redraw);
    assert!(!engine.update(Duration::ZERO, Controls::default()).redraw);
    assert!(
        !engine
            .update(Duration::from_millis(1999), Controls::default())
            .redraw
    );
    let first = frame(&engine);
    assert!(
        engine
            .update(Duration::from_millis(1), Controls::default())
            .redraw
    );
    assert_ne!(first, frame(&engine));
    assert_eq!(engine.screen(), Screen::Splash);
    assert!(
        engine
            .update(Duration::from_secs(2), Controls::default())
            .redraw
    );
    assert_eq!(engine.screen(), Screen::App(AppId::Names));
}

#[test]
fn menu_wraps_and_held_buttons_do_not_repeat() {
    let mut engine = Engine::new();
    main_menu(&mut engine);
    let up = Controls {
        dpad_up: true,
        ..Controls::default()
    };
    assert!(engine.update(Duration::ZERO, up).redraw);
    assert_eq!(engine.selected_entry(), 3);
    assert!(!engine.update(Duration::from_secs(1), up).redraw);
    down(&mut engine);
    assert_eq!(engine.selected_entry(), 0);
    down(&mut engine);
    assert_eq!(engine.selected_entry(), 1);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::Menu(WATCH));
    assert_eq!(engine.selected_entry(), 0);
    back(&mut engine);
    assert_eq!(engine.screen(), Screen::Menu(ROOT));
    assert_eq!(engine.selected_entry(), 1);
    let _ = enter(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::App(AppId::Hyper));
    back(&mut engine);
    assert_eq!(engine.screen(), Screen::Menu(WATCH));
    assert_eq!(engine.selected_entry(), 1);
}

#[test]
fn music_is_requested_once_on_entry_and_stopped_on_exit() {
    let mut engine = Engine::new();
    main_menu(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(enter(&mut engine).audio, Some(AudioId::MusicNyan));
    assert_eq!(engine.screen(), Screen::App(AppId::Nyan));
    for _ in 0..30 {
        assert_eq!(
            engine
                .update(Duration::from_millis(10), Controls::default())
                .audio,
            None
        );
    }
    assert_eq!(
        tap(
            &mut engine,
            Controls {
                buttons_b: true,
                ..Controls::default()
            }
        )
        .audio,
        Some(AudioId::Stop)
    );
    assert_eq!(engine.screen(), Screen::Menu(WATCH));
    assert!(AudioId::MusicNyan.file().is_some());
    assert_eq!(AudioId::Stop.file(), None);
}

#[test]
fn animation_timing_retains_fractional_intervals() {
    fn nyan() -> Engine {
        let mut engine = Engine::new();
        main_menu(&mut engine);
        down(&mut engine);
        let _ = enter(&mut engine);
        let _ = enter(&mut engine);
        engine
    }
    let mut whole = nyan();
    let mut split = nyan();
    let _ = whole.update(Duration::from_millis(125), Controls::default());
    for _ in 0..5 {
        let _ = split.update(Duration::from_millis(25), Controls::default());
    }
    assert_eq!(frame(&whole), frame(&split));
    let _ = whole.update(Duration::MAX, Controls::default());
    let _ = frame(&whole);
}

#[test]
fn every_public_screen_renders_within_display_bounds() {
    let mut engine = Engine::new();
    let _ = frame(&engine);
    main_menu(&mut engine);
    let _ = frame(&engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::App(AppId::Names));
    for _ in 0..1000 {
        let _ = engine.update(Duration::from_millis(250), Controls::default());
        let _ = frame(&engine);
    }
    back(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::Menu(WATCH));
    let _ = frame(&engine);
    for expected in [AppId::Nyan, AppId::Hyper, AppId::Fire] {
        let _ = enter(&mut engine);
        assert_eq!(engine.screen(), Screen::App(expected));
        for _ in 0..15 {
            let _ = engine.update(Duration::from_millis(50), Controls::default());
            let _ = frame(&engine);
        }
        back(&mut engine);
        down(&mut engine);
    }
    back(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::Menu(PLAY));
    let _ = frame(&engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::App(AppId::Pong));
    for _ in 0..2000 {
        let _ = engine.update(
            Duration::from_millis(250),
            Controls {
                dpad_down: true,
                ..Controls::default()
            },
        );
        let _ = frame(&engine);
    }
    back(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.screen(), Screen::App(AppId::Snake));
    for _ in 0..40 {
        let _ = engine.update(Duration::from_millis(60), Controls::default());
        let _ = frame(&engine);
    }
    assert!(engine.game_over());
    let _ = enter(&mut engine);
    assert!(!engine.game_over());
}

#[test]
fn long_game_stalls_have_bounded_catch_up() {
    fn pong() -> Engine {
        let mut engine = Engine::new();
        main_menu(&mut engine);
        down(&mut engine);
        down(&mut engine);
        let _ = enter(&mut engine);
        let _ = enter(&mut engine);
        engine
    }
    let mut long = pong();
    let mut capped = pong();
    let _ = long.update(Duration::MAX, Controls::default());
    let _ = capped.update(Duration::from_millis(250), Controls::default());
    assert_eq!(frame(&long), frame(&capped));
}

#[test]
fn render_propagates_device_errors() {
    struct Broken;
    impl OriginDimensions for Broken {
        fn size(&self) -> Size {
            Size::new(WIDTH, HEIGHT)
        }
    }
    impl DrawTarget for Broken {
        type Color = Rgb565;
        type Error = &'static str;
        fn draw_iter<I>(&mut self, _: I) -> Result<(), Self::Error>
        where
            I: IntoIterator<Item = Pixel<Self::Color>>,
        {
            Err("disconnected")
        }
    }
    assert_eq!(Engine::new().render(&mut Broken), Err("disconnected"));
}

#[test]
fn deadlines_follow_splash_boundaries_and_idle_screens_sleep() {
    let mut engine = Engine::new();
    assert_eq!(engine.next_update_after(), Some(Duration::from_secs(2)));
    let _ = engine.update(Duration::from_millis(1999), Controls::default());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(1)));
    let _ = engine.update(Duration::from_millis(1), Controls::default());
    assert_eq!(engine.next_update_after(), Some(Duration::from_secs(2)));
    let _ = engine.update(Duration::from_secs(2), Controls::default());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(30)));
    main_menu(&mut engine);
    assert_eq!(engine.next_update_after(), None);
    let _ = engine.update(Duration::from_secs(60), Controls::default());
    assert_eq!(engine.next_update_after(), None);
    let _ = engine.open_canvas();
    assert_eq!(engine.next_update_after(), None);
}

#[test]
fn event_wakes_preserve_animation_deadlines_without_drift() {
    let mut engine = Engine::new();
    main_menu(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    for app in [AppId::Nyan, AppId::Hyper, AppId::Fire] {
        let _ = enter(&mut engine);
        assert_eq!(engine.screen(), Screen::App(app));
        let period = if app == AppId::Fire { 100 } else { 50 };
        for elapsed in 1..period {
            assert!(
                !engine
                    .update(Duration::from_millis(1), Controls::default())
                    .redraw
            );
            assert_eq!(
                engine.next_update_after(),
                Some(Duration::from_millis(period - elapsed))
            );
        }
        assert!(
            engine
                .update(Duration::from_millis(1), Controls::default())
                .redraw
        );
        assert_eq!(
            engine.next_update_after(),
            Some(Duration::from_millis(period))
        );
        back(&mut engine);
        down(&mut engine);
    }
}

#[test]
fn games_schedule_ticks_and_finished_snake_sleeps_until_input() {
    let mut engine = Engine::new();
    main_menu(&mut engine);
    down(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(20)));
    let _ = engine.update(Duration::from_millis(7), Controls::default());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(13)));
    back(&mut engine);
    down(&mut engine);
    let _ = enter(&mut engine);
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(60)));
    for _ in 0..40 {
        if engine.game_over() {
            break;
        }
        let deadline = engine.next_update_after().expect("live game tick");
        let _ = engine.update(deadline, Controls::default());
    }
    assert!(engine.game_over());
    assert_eq!(engine.next_update_after(), None);
    let _ = enter(&mut engine);
    assert!(!engine.game_over());
    assert_eq!(engine.next_update_after(), Some(Duration::from_millis(60)));
}
