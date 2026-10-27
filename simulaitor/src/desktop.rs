use super::{Framebuffer, render};
use aitos::{audio::OutputPlayer, input::Debouncer};
use displaitor::{AudioId, Controls, Engine, HEIGHT, WIDTH};
use sdl2::{
    audio::{AudioCallback, AudioSpecDesired},
    event::{Event, WindowEvent},
    keyboard::Keycode,
    pixels::PixelFormatEnum,
};
use std::time::{Duration, Instant};

pub fn run(
    frames: Option<u32>,
    mut link: Option<super::canvas_link::CanvasLink>,
) -> Result<(), String> {
    if frames == Some(0) {
        return Err("--frames must be greater than zero".into());
    }
    let sdl = sdl2::init()?;
    let video = sdl.video()?;
    let window = video
        .window("Displaitor", WIDTH * 12, HEIGHT * 12)
        .position_centered()
        .resizable()
        .build()
        .map_err(|error| error.to_string())?;
    let mut canvas = window
        .into_canvas()
        .present_vsync()
        .build()
        .map_err(|error| error.to_string())?;
    canvas
        .set_logical_size(WIDTH, HEIGHT)
        .map_err(|error| error.to_string())?;
    let textures = canvas.texture_creator();
    let mut texture = textures
        .create_texture_streaming(PixelFormatEnum::RGB24, WIDTH, HEIGHT)
        .map_err(|error| error.to_string())?;
    let mut bytes = vec![0_u8; (WIDTH * HEIGHT * 3) as usize];
    let mut framebuffer = Framebuffer::new();
    let mut engine = Engine::new();
    if link.is_some() {
        let _ = engine.open_canvas();
    }
    let mut controls = Controls::default();
    let mut debounce = Debouncer::default();
    let mut mute_pressed = false;
    let mut muted = false;
    let mut events = sdl.event_pump()?;
    let audio = sdl.audio()?;
    let desired = AudioSpecDesired {
        freq: Some(44_100),
        channels: Some(1),
        samples: Some(512),
    };
    let mut device = audio.open_playback(None, &desired, |spec| Playback::new(spec.freq as u32))?;
    device.resume();
    let mut last_update = Instant::now();
    let mut dirty = true;
    let mut frame_count = 0_u32;
    println!("W/S/A/D: directions; Space: A/select; Q: B/back; R: mute on release; Escape: quit");
    'running: loop {
        for event in events.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown {
                    keycode: Some(Keycode::Escape),
                    ..
                } => break 'running,
                Event::Window {
                    win_event: WindowEvent::FocusLost,
                    ..
                } => {
                    controls = Controls::default();
                    // Losing focus cancels held keys instead of causing a mute toggle.
                    mute_pressed = false;
                    debounce = Debouncer::default();
                }
                Event::Window {
                    win_event: WindowEvent::Exposed | WindowEvent::Resized(..),
                    ..
                } => dirty = true,
                Event::KeyDown {
                    keycode: Some(key),
                    repeat: false,
                    ..
                } => set_key(&mut controls, key, true),
                Event::KeyUp {
                    keycode: Some(key), ..
                } => set_key(&mut controls, key, false),
                _ => {}
            }
        }
        let now = Instant::now();
        let dt = now.duration_since(last_update);
        last_update = now;
        let stable = debounce.update(dt, controls);
        if mute_pressed && !stable.buttons_s {
            muted = !muted;
            device.lock().player.set_enabled(!muted);
            println!("Audio {}", if muted { "muted" } else { "enabled" });
        }
        mute_pressed = stable.buttons_s;
        if let Some(link) = &mut link {
            link.service(&mut engine)?;
        }
        let update = engine.update(dt, stable);
        if let Some(id) = update.audio {
            device.lock().select(id);
        }
        if update.redraw {
            render(&engine, &mut framebuffer);
            dirty = true;
        }
        if dirty {
            framebuffer.rgb_bytes(&mut bytes);
            texture
                .update(None, &bytes, WIDTH as usize * 3)
                .map_err(|error| error.to_string())?;
            canvas.clear();
            canvas.copy(&texture, None, None)?;
            canvas.present();
            dirty = false;
        }
        frame_count = frame_count.saturating_add(1);
        if frames.is_some_and(|limit| frame_count >= limit) {
            break;
        }
        std::thread::sleep(Duration::from_millis(1));
    }
    Ok(())
}

fn set_key(controls: &mut Controls, key: Keycode, pressed: bool) {
    match key {
        Keycode::W => controls.dpad_up = pressed,
        Keycode::S => controls.dpad_down = pressed,
        Keycode::A => controls.dpad_left = pressed,
        Keycode::D => controls.dpad_right = pressed,
        Keycode::Space => controls.buttons_a = pressed,
        Keycode::Q => controls.buttons_b = pressed,
        Keycode::R => controls.buttons_s = pressed,
        _ => {}
    }
}

struct Playback {
    player: OutputPlayer,
}

impl Playback {
    fn new(output_rate: u32) -> Self {
        Self {
            player: OutputPlayer::new(output_rate),
        }
    }

    fn select(&mut self, id: AudioId) {
        if let Err(error) = self.player.select(id) {
            eprintln!("Cannot play {id:?}: {error:?}");
        }
    }
}

impl AudioCallback for Playback {
    type Channel = i16;

    fn callback(&mut self, output: &mut [i16]) {
        for sample in output {
            *sample = self.player.next_sample().ok().flatten().unwrap_or_default();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn key_mapping_uses_pressed_polarity() {
        let mut controls = Controls::default();
        set_key(&mut controls, Keycode::W, true);
        set_key(&mut controls, Keycode::Space, true);
        assert!(controls.dpad_up && controls.buttons_a);
        set_key(&mut controls, Keycode::W, false);
        assert!(!controls.dpad_up && controls.buttons_a);
        for (index, key) in [Keycode::W, Keycode::S, Keycode::A, Keycode::D]
            .into_iter()
            .enumerate()
        {
            set_key(&mut controls, key, true);
            assert_eq!(
                [
                    controls.dpad_up,
                    controls.dpad_down,
                    controls.dpad_left,
                    controls.dpad_right
                ],
                core::array::from_fn(|direction| direction == index),
            );
            set_key(&mut controls, key, false);
        }
    }

    #[test]
    fn resampled_audio_mutes_resumes_and_stops() {
        let mut playback = Playback::new(48_000);
        playback.select(AudioId::Ping);
        let mut prefix = [0_i16; 1024];
        playback.callback(&mut prefix);
        assert!(prefix.iter().any(|sample| *sample != 0));
        playback.player.set_enabled(false);
        playback.callback(&mut prefix);
        assert!(prefix.iter().all(|sample| *sample == 0));
        playback.player.set_enabled(true);
        playback.callback(&mut prefix);
        assert!(prefix.iter().any(|sample| *sample != 0));
        playback.select(AudioId::Stop);
        playback.callback(&mut prefix);
        assert!(prefix.iter().all(|sample| *sample == 0));
    }
}
