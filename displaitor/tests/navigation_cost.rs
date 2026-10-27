use core::convert::Infallible;
use core::time::Duration;

use displaitor::{
    AppId, Controls, Engine, HEIGHT, WIDTH,
    navigation::{Action, Entry, Menu, MenuId},
};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

const MENU_DEPTHS: [usize; 4] = [1, 16, 64, 128];
const GRAPH_SIZE: usize = 130;

struct Frame {
    pixels: [Rgb565; (WIDTH * HEIGHT) as usize],
    emitted: usize,
    batches: usize,
}

impl Default for Frame {
    fn default() -> Self {
        Self {
            pixels: [Rgb565::BLACK; (WIDTH * HEIGHT) as usize],
            emitted: 0,
            batches: 0,
        }
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
        self.batches += 1;
        for Pixel(point, color) in pixels {
            assert!((0..WIDTH as i32).contains(&point.x));
            assert!((0..HEIGHT as i32).contains(&point.y));
            self.emitted += 1;
            self.pixels[point.y as usize * WIDTH as usize + point.x as usize] = color;
        }
        Ok(())
    }
}

fn engine_with_chain() -> Engine<GRAPH_SIZE> {
    // Host-only graph construction. Every menu has one identically rendered
    // folder row, so a depth change cannot alter menu content or row count.
    let entries: Vec<&'static [Entry<'static>]> = (0..GRAPH_SIZE)
        .map(|index| {
            let child = if index + 1 < GRAPH_SIZE {
                Action::Menu(MenuId::new(index + 1))
            } else {
                Action::App(AppId::Pong)
            };
            Box::leak(
                vec![
                    Entry::new("Start", Action::App(AppId::Names)),
                    Entry::new("Open", child),
                ]
                .into_boxed_slice(),
            ) as &'static [Entry<'static>]
        })
        .collect();
    let menus = (0..GRAPH_SIZE)
        .map(|index| {
            let parent = (index > 0).then(|| MenuId::new(index - 1));
            Menu::new("MENU", parent, entries[index])
        })
        .collect::<Vec<_>>()
        .into_boxed_slice();
    let menus: &'static mut [Menu<'static>; GRAPH_SIZE] =
        Box::leak(menus.try_into().expect("fixed graph size"));
    Engine::with_menus(menus, MenuId::new(0)).expect("valid chain")
}

fn tap<const N: usize>(engine: &mut Engine<N>, controls: Controls) {
    let _ = engine.update(Duration::ZERO, Controls::default());
    let _ = engine.update(Duration::ZERO, controls);
    let _ = engine.update(Duration::ZERO, Controls::default());
}

fn enter_root<const N: usize>(engine: &mut Engine<N>) {
    let back = Controls {
        buttons_b: true,
        ..Controls::default()
    };
    tap(engine, back); // Splash -> Names
    tap(engine, back); // Names -> root menu
}

fn descend<const N: usize>(engine: &mut Engine<N>, depth: usize) {
    enter_root(engine);
    let select = Controls {
        buttons_a: true,
        ..Controls::default()
    };
    for _ in 0..depth {
        tap(
            engine,
            Controls {
                dpad_down: true,
                ..Controls::default()
            },
        );
        tap(engine, select);
    }
}

#[test]
fn deep_menu_navigation_and_back_use_the_active_path() {
    let mut engine = engine_with_chain();
    descend(&mut engine, GRAPH_SIZE - 1);
    assert_eq!(engine.navigation().menu_id(), MenuId::new(GRAPH_SIZE - 1));

    for expected in (0..GRAPH_SIZE - 1).rev() {
        let back = Controls {
            buttons_b: true,
            ..Controls::default()
        };
        tap(&mut engine, back);
        assert_eq!(engine.navigation().menu_id(), MenuId::new(expected));
        assert_eq!(engine.navigation().selected_index(), 1);
    }
}

#[test]
fn reused_leaf_app_returns_to_its_own_menu_and_cursor() {
    const LEFT_ENTRIES: [Entry<'static>; 2] = [
        Entry::new("Pong", Action::App(AppId::Pong)),
        Entry::new("Pong", Action::App(AppId::Pong)),
    ];
    const RIGHT_ENTRIES: [Entry<'static>; 2] = [
        Entry::new("Other", Action::App(AppId::Names)),
        Entry::new("Pong", Action::App(AppId::Pong)),
    ];
    const MENUS: [Menu<'static>; 3] = [
        Menu::new(
            "ROOT",
            None,
            &[
                Entry::new("Left", Action::Menu(MenuId::new(1))),
                Entry::new("Right", Action::Menu(MenuId::new(2))),
            ],
        ),
        Menu::new("LEFT", Some(MenuId::new(0)), &LEFT_ENTRIES),
        Menu::new("RIGHT", Some(MenuId::new(0)), &RIGHT_ENTRIES),
    ];
    let mut engine = Engine::<3>::with_menus(&MENUS, MenuId::new(0)).unwrap();
    enter_root(&mut engine);

    tap(
        &mut engine,
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            dpad_down: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), displaitor::Screen::App(AppId::Pong));
    tap(
        &mut engine,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.navigation().menu_id(), MenuId::new(1));
    assert_eq!(engine.navigation().selected_index(), 1);

    tap(
        &mut engine,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            dpad_down: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            dpad_down: true,
            ..Controls::default()
        },
    );
    tap(
        &mut engine,
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.screen(), displaitor::Screen::App(AppId::Pong));
    tap(
        &mut engine,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.navigation().menu_id(), MenuId::new(2));
    assert_eq!(engine.navigation().selected_index(), 1);
}

#[test]
fn rendered_work_is_independent_of_active_menu_depth() {
    let mut reference: Option<(Vec<Rgb565>, usize, usize)> = None;
    for depth in MENU_DEPTHS {
        let mut engine = engine_with_chain();
        descend(&mut engine, depth);
        assert_eq!(engine.navigation().menu_id(), MenuId::new(depth));
        let mut frame = Frame::default();
        engine.render(&mut frame).unwrap();
        let result = (frame.pixels.to_vec(), frame.emitted, frame.batches);
        if let Some(expected) = &reference {
            assert_eq!(&result, expected, "render work changed at depth {depth}");
        } else {
            reference = Some(result);
        }
    }
}

#[test]
fn running_app_update_and_render_work_is_independent_of_origin_depth() {
    type AppSnapshot = (displaitor::Update, Vec<Rgb565>, usize, usize);
    let mut reference: Option<Vec<AppSnapshot>> = None;
    for depth in MENU_DEPTHS {
        let mut engine = engine_with_chain();
        descend(&mut engine, depth);
        tap(
            &mut engine,
            Controls {
                buttons_a: true,
                ..Controls::default()
            },
        );
        assert_eq!(engine.screen(), displaitor::Screen::App(AppId::Names));

        let mut frames = Vec::new();
        for elapsed in [
            Duration::from_millis(30),
            Duration::from_secs(1),
            Duration::MAX,
        ] {
            let update = engine.update(elapsed, Controls::default());
            let mut frame = Frame::default();
            engine.render(&mut frame).unwrap();
            frames.push((update, frame.pixels.to_vec(), frame.emitted, frame.batches));
        }

        let back = Controls {
            buttons_b: true,
            ..Controls::default()
        };
        tap(&mut engine, back);
        assert_eq!(engine.navigation().menu_id(), MenuId::new(depth));
        assert_eq!(engine.navigation().selected_index(), 0);

        if let Some(expected_frames) = &reference {
            assert_eq!(
                &frames, expected_frames,
                "app work changed at depth {depth}"
            );
        } else {
            reference = Some(frames);
        }
    }
}

#[test]
fn canvas_work_is_independent_of_origin_depth() {
    let mut reference = None;
    for depth in MENU_DEPTHS {
        let mut engine = engine_with_chain();
        descend(&mut engine, depth);
        let _ = engine.open_canvas();
        engine.canvas_mut().apply(5, &[0xe0, 7]).unwrap();
        let update = engine.update(Duration::ZERO, Controls::default());
        let idle = engine.update(Duration::MAX, Controls::default());
        assert!(update.redraw && !idle.redraw);
        let mut frame = Frame::default();
        engine.render(&mut frame).unwrap();
        let result = (
            update,
            idle,
            frame.pixels.to_vec(),
            frame.emitted,
            frame.batches,
        );
        if let Some(expected) = &reference {
            assert_eq!(&result, expected, "Canvas work changed at depth {depth}");
        } else {
            reference = Some(result);
        }
        tap(
            &mut engine,
            Controls {
                buttons_b: true,
                ..Controls::default()
            },
        );
        assert_eq!(engine.navigation().menu_id(), MenuId::new(depth));
    }
}

#[test]
fn empty_and_invalid_graphs_have_explicit_errors() {
    const EMPTY_ENTRIES: [Entry<'static>; 0] = [];
    const EMPTY_MENU: [Menu<'static>; 1] = [Menu::new("EMPTY", None, &EMPTY_ENTRIES)];
    const ONE_ENTRY: [Entry<'static>; 1] = [Entry::new("Next", Action::Menu(MenuId::new(2)))];
    const BAD_LINK: [Menu<'static>; 2] = [
        Menu::new("ROOT", None, &ONE_ENTRY),
        Menu::new("ORPHAN", Some(MenuId::new(0)), &EMPTY_ENTRIES),
    ];
    const CYCLE_ROOT_ENTRY: [Entry<'static>; 1] =
        [Entry::new("Child", Action::Menu(MenuId::new(1)))];
    const CYCLE_CHILD_ENTRY: [Entry<'static>; 1] =
        [Entry::new("Root", Action::Menu(MenuId::new(0)))];
    const CYCLE: [Menu<'static>; 2] = [
        Menu::new("ROOT", None, &CYCLE_ROOT_ENTRY),
        Menu::new("CHILD", Some(MenuId::new(0)), &CYCLE_CHILD_ENTRY),
    ];
    assert_eq!(
        Engine::with_menus(&EMPTY_MENU, MenuId::new(0)).err(),
        Some(displaitor::navigation::NavigationError::EmptyMenu(
            MenuId::new(0)
        ))
    );
    assert_eq!(
        Engine::with_menus(&BAD_LINK, MenuId::new(0)).err(),
        Some(displaitor::navigation::NavigationError::InvalidParent(
            MenuId::new(2)
        ))
    );
    assert_eq!(
        Engine::with_menus(&CYCLE, MenuId::new(0)).err(),
        Some(displaitor::navigation::NavigationError::Cycle(MenuId::new(
            0
        )))
    );
}
