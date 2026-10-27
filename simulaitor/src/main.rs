use aitos::input::Debouncer;
use core::convert::Infallible;
use displaitor::{AppId, Controls, DEFAULT_MENU_COUNT, Engine, HEIGHT, Screen, WIDTH};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
use std::time::Duration;

mod canvas_link;
#[cfg(feature = "sdl")]
mod desktop;
mod framebuffer;

use framebuffer::Framebuffer;

fn main() -> Result<(), String> {
    let mut headless = false;
    let mut frames: Option<u32> = None;
    let mut smoke = false;
    let mut canvas_address = None;
    let mut snapshot = None;
    let mut arguments = std::env::args().skip(1);
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--canvas-listen" => {
                canvas_address = Some(arguments.next().ok_or("--canvas-listen requires IP:port")?)
            }
            "--snapshot" => {
                snapshot = Some(arguments.next().ok_or("--snapshot requires a PPM path")?)
            }
            "--headless" => headless = true,
            "--smoke" => {
                headless = true;
                smoke = true;
            }
            "--frames" => {
                frames = Some(
                    arguments
                        .next()
                        .ok_or("--frames requires a count")?
                        .parse()
                        .map_err(|_| "--frames requires an unsigned integer")?,
                );
            }
            "--help" | "-h" => {
                println!(
                    "simulaitor [--headless | --smoke] [--frames N] [--canvas-listen 127.0.0.1:7777] [--snapshot frame.ppm]\n\nW/S/A/D: directions; Space: A/select; Q: B/back; R: mute on release\nEscape: quit. --smoke exercises every application without SDL or audio.\n--canvas-listen locally opens Canvas. Headless Canvas runs in real time."
                );
                return Ok(());
            }
            _ => return Err(format!("unknown argument: {argument}")),
        }
    }
    if smoke && canvas_address.is_some() {
        return Err("--smoke and --canvas-listen are separate modes".into());
    }
    if snapshot.is_some() && !headless {
        return Err("--snapshot requires --headless".into());
    }
    let link = canvas_address
        .as_deref()
        .map(canvas_link::CanvasLink::bind)
        .transpose()?;
    if headless {
        return run_headless(frames.unwrap_or(600), smoke, link, snapshot.as_deref());
    }
    #[cfg(feature = "sdl")]
    {
        desktop::run(frames, link)
    }
    #[cfg(not(feature = "sdl"))]
    {
        Err("desktop support is disabled; use --headless or build with --features sdl".into())
    }
}

fn render(engine: &Engine, framebuffer: &mut Framebuffer) {
    framebuffer.clear(Rgb565::BLACK).unwrap();
    let result: Result<(), Infallible> = engine.render(framebuffer);
    result.unwrap();
}

fn run_headless(
    frames: u32,
    smoke: bool,
    mut link: Option<canvas_link::CanvasLink>,
    snapshot: Option<&str>,
) -> Result<(), String> {
    if frames == 0 {
        return Err("--frames must be greater than zero".into());
    }
    let mut engine = Engine::new();
    if link.is_some() {
        let _ = engine.open_canvas();
    }
    let mut framebuffer = Framebuffer::new();
    if smoke && frames < 390 {
        return Err("--smoke requires at least 390 frames".into());
    }
    let mut debounce = Debouncer::default();
    let mut visited = [false; 1 + DEFAULT_MENU_COUNT + AppId::COUNT];
    let mut redraws = 0;
    let mut audio_requests = 0;
    let mut checksum = 0_u64;
    render(&engine, &mut framebuffer);
    let mut saw_visible_pixels = framebuffer.has_visible_pixels();
    for frame in 0..frames {
        if let Some(link) = &mut link {
            link.service(&mut engine)?;
        }
        let controls = if smoke {
            smoke_input(frame)
        } else {
            Controls::default()
        };
        let controls = debounce.update(Duration::from_millis(10), controls);
        let update = engine.update(Duration::from_millis(10), controls);
        visited[screen_index(engine.screen())] = true;
        audio_requests += u32::from(update.audio.is_some());
        if update.redraw {
            render(&engine, &mut framebuffer);
            saw_visible_pixels |= framebuffer.has_visible_pixels();
            redraws += 1;
            checksum = checksum.rotate_left(7) ^ framebuffer.checksum();
        }
        if link.is_some() {
            std::thread::sleep(Duration::from_millis(10));
        }
    }
    if redraws == 0 || (!saw_visible_pixels && link.is_none()) {
        return Err("headless rendering did not produce a visible frame".into());
    }
    if smoke {
        for menu in 0..DEFAULT_MENU_COUNT {
            if !visited[1 + menu] {
                return Err(format!("smoke did not visit menu {menu}"));
            }
        }
        for screen in
            core::iter::once(Screen::Splash).chain(AppId::ALL.iter().copied().map(Screen::App))
        {
            if !visited[screen_index(screen)] {
                return Err(format!("smoke did not visit {screen:?}"));
            }
        }
    }
    if let Some(path) = snapshot {
        framebuffer.write_ppm(path)?;
    }
    println!(
        "{WIDTH}x{HEIGHT}: frames={frames} redraws={redraws} audio_requests={audio_requests} checksum={checksum:016x} screen={:?}",
        engine.screen()
    );
    Ok(())
}

fn smoke_input(frame: u32) -> Controls {
    // Every press spans three 10 ms updates, followed by at least 70 ms released.
    // Skip splash, open menu, animations and each child, then games.
    let mut controls = Controls::default();
    let button = match frame {
        5..=7
        | 20..=22
        | 100..=102
        | 150..=152
        | 200..=202
        | 220..=222
        | 290..=292
        | 350..=352
        | 360..=362 => 1,
        30..=32 | 110..=112 | 160..=162 | 230..=232 | 300..=302 | 370..=372 => 2,
        40..=42
        | 70..=72
        | 120..=122
        | 170..=172
        | 240..=242
        | 250..=252
        | 320..=322
        | 380..=382 => 3,
        _ => 0,
    };
    match button {
        1 => controls.buttons_b = true,
        2 => controls.dpad_down = true,
        3 => controls.buttons_a = true,
        _ => {}
    }
    controls
}

fn screen_index(screen: Screen) -> usize {
    match screen {
        Screen::Splash => 0,
        Screen::Menu(id) => 1 + id.index(),
        Screen::App(id) => 1 + DEFAULT_MENU_COUNT + id as usize,
    }
}
