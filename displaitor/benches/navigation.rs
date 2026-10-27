use core::{convert::Infallible, hint::black_box, time::Duration};
use std::{boxed::Box, time::Instant};

use displaitor::{
    AppId, Controls, Engine, HEIGHT, WIDTH,
    navigation::{Action, Entry, Menu, MenuId},
};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

const GRAPH_SIZE: usize = 131;
const DEPTHS: [usize; 4] = [1, 16, 64, 128];
const SAMPLES: usize = 3;
const IDLE_UPDATES: usize = 200_000;
const NAV_PAIRS: usize = 100_000;
const RENDER_FRAMES: usize = 5_000;

struct PixelSink {
    pixels: usize,
    batches: usize,
    hash: u32,
}

impl Default for PixelSink {
    fn default() -> Self {
        Self {
            pixels: 0,
            batches: 0,
            hash: 2_166_136_261,
        }
    }
}

impl OriginDimensions for PixelSink {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}

impl DrawTarget for PixelSink {
    type Color = Rgb565;
    type Error = Infallible;

    fn draw_iter<I>(&mut self, pixels: I) -> Result<(), Self::Error>
    where
        I: IntoIterator<Item = Pixel<Self::Color>>,
    {
        self.batches += 1;
        for Pixel(point, color) in pixels {
            self.pixels += 1;
            let packed = (point.x as u32).wrapping_mul(0x9e37_79b1)
                ^ (point.y as u32).rotate_left(11)
                ^ (u32::from(color.r()) << 16)
                ^ (u32::from(color.g()) << 8)
                ^ u32::from(color.b());
            self.hash = self.hash.wrapping_mul(16_777_619) ^ packed;
        }
        Ok(())
    }
}

fn chain() -> &'static [Menu<'static>; GRAPH_SIZE] {
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
            let parent = if index == 0 {
                None
            } else {
                Some(MenuId::new(index - 1))
            };
            Menu::new("MENU", parent, entries[index])
        })
        .collect::<Vec<_>>()
        .into_boxed_slice();
    Box::leak(menus.try_into().expect("fixed graph size"))
}

fn tap<const N: usize>(engine: &mut Engine<N>, controls: Controls) {
    let _ = black_box(engine.update(Duration::ZERO, Controls::default()));
    let _ = black_box(engine.update(Duration::ZERO, controls));
    let _ = black_box(engine.update(Duration::ZERO, Controls::default()));
}

fn at_depth(menus: &'static [Menu<'static>; GRAPH_SIZE], depth: usize) -> Engine<GRAPH_SIZE> {
    let mut engine = Engine::with_menus(menus, MenuId::new(0)).expect("valid static chain");
    let back = Controls {
        buttons_b: true,
        ..Controls::default()
    };
    tap(&mut engine, back); // Splash -> Names
    tap(&mut engine, back); // Names -> root menu
    for _ in 0..depth {
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
    }
    engine
}

fn ns_per_op<F>(mut operation: F, iterations: usize) -> f64
where
    F: FnMut(),
{
    let start = Instant::now();
    for _ in 0..iterations {
        operation();
    }
    start.elapsed().as_nanos() as f64 / iterations as f64
}

fn median3(mut values: [f64; SAMPLES]) -> f64 {
    values.sort_by(f64::total_cmp);
    values[1]
}

fn main() {
    // Cargo may build and invoke a `harness = false` bench as part of
    // `cargo test --all-targets`; that validation run should not benchmark.
    if cfg!(debug_assertions) || std::env::args().any(|argument| argument == "--test") {
        return;
    }

    let menus = chain(); // Graph allocation and validation are outside measurements.
    println!("release host benchmark; median of {SAMPLES} samples; no timing assertions");
    println!(
        "depth  idle_update_ns  direction_pair_ns  enter_back_pair_ns  render_ns/frame  pixels/frame  batches/frame  hash"
    );

    for depth in DEPTHS {
        let mut idle_samples = [0.0; SAMPLES];
        let mut direction_samples = [0.0; SAMPLES];
        let mut enter_back_samples = [0.0; SAMPLES];
        let mut render_samples = [0.0; SAMPLES];
        let mut last_sink = PixelSink::default();

        for sample in 0..SAMPLES {
            let mut idle_engine = at_depth(menus, depth);
            idle_samples[sample] = ns_per_op(
                || {
                    let result = idle_engine.update(Duration::ZERO, black_box(Controls::default()));
                    let _ = black_box(result);
                    black_box(idle_engine.navigation().menu_id());
                },
                IDLE_UPDATES,
            );

            let mut navigation_engine = at_depth(menus, depth);
            direction_samples[sample] = ns_per_op(
                || {
                    let down = Controls {
                        dpad_down: true,
                        ..Controls::default()
                    };
                    let up = Controls {
                        dpad_up: true,
                        ..Controls::default()
                    };
                    let _ = black_box(navigation_engine.update(Duration::ZERO, black_box(down)));
                    let _ = black_box(navigation_engine.update(Duration::ZERO, black_box(up)));
                    black_box(navigation_engine.navigation().selected_index());
                },
                NAV_PAIRS,
            );

            let mut transition_engine = at_depth(menus, depth);
            tap(
                &mut transition_engine,
                Controls {
                    dpad_down: true,
                    ..Controls::default()
                },
            );
            enter_back_samples[sample] = ns_per_op(
                || {
                    let enter = Controls {
                        buttons_a: true,
                        ..Controls::default()
                    };
                    let back = Controls {
                        buttons_b: true,
                        ..Controls::default()
                    };
                    let _ = black_box(transition_engine.update(Duration::ZERO, black_box(enter)));
                    let _ = black_box(transition_engine.update(Duration::ZERO, black_box(back)));
                    black_box(transition_engine.navigation().menu_id());
                },
                NAV_PAIRS,
            );

            let render_engine = at_depth(menus, depth);
            render_samples[sample] = ns_per_op(
                || {
                    let mut sink = PixelSink::default();
                    black_box(&render_engine)
                        .render(black_box(&mut sink))
                        .expect("infallible sink");
                    black_box((sink.pixels, sink.batches, sink.hash));
                    last_sink = sink;
                },
                RENDER_FRAMES,
            );
        }

        println!(
            "{depth:>5}  {:>14.2}  {:>18.2}  {:>18.2}  {:>15.2}  {:>12}  {:>13}  {:08x}",
            median3(idle_samples),
            median3(direction_samples),
            median3(enter_back_samples),
            median3(render_samples),
            last_sink.pixels,
            last_sink.batches,
            last_sink.hash,
        );
    }
}
