//! Export actual application menu frames without SDL or hardware.
use displaitor::{Controls, Engine, HEIGHT, WIDTH};
use embedded_graphics::{
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
};
use std::{fs, path::Path, time::Duration};

struct Frame([Rgb565; (WIDTH * HEIGHT) as usize]);
impl OriginDimensions for Frame {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}
impl DrawTarget for Frame {
    type Color = Rgb565;
    type Error = core::convert::Infallible;
    fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
        &mut self,
        pixels: I,
    ) -> Result<(), Self::Error> {
        for Pixel(p, c) in pixels {
            assert!((0..WIDTH as i32).contains(&p.x) && (0..HEIGHT as i32).contains(&p.y));
            self.0[p.y as usize * WIDTH as usize + p.x as usize] = c;
        }
        Ok(())
    }
}
fn tap(engine: &mut Engine, controls: Controls) {
    let _ = engine.update(Duration::ZERO, Controls::default());
    let _ = engine.update(Duration::ZERO, controls);
    let _ = engine.update(Duration::ZERO, Controls::default());
}
fn capture(engine: &Engine, path: &Path) -> std::io::Result<()> {
    let mut frame = Frame([Rgb565::BLACK; (WIDTH * HEIGHT) as usize]);
    engine.render(&mut frame).unwrap();
    let mut bytes = format!("P6\n{WIDTH} {HEIGHT}\n255\n").into_bytes();
    for pixel in frame.0 {
        let c = Rgb888::from(pixel);
        bytes.extend_from_slice(&[c.r(), c.g(), c.b()]);
    }
    fs::write(path, bytes)
}
fn main() -> std::io::Result<()> {
    let directory = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "target/ui-preview".into());
    let directory = Path::new(&directory);
    fs::create_dir_all(directory)?;
    let mut engine = Engine::new();
    let back = Controls {
        buttons_b: true,
        ..Controls::default()
    };
    let down = Controls {
        dpad_down: true,
        ..Controls::default()
    };
    let activate = Controls {
        buttons_a: true,
        ..Controls::default()
    };
    tap(&mut engine, back);
    tap(&mut engine, back);
    capture(&engine, &directory.join("root.ppm"))?;
    tap(&mut engine, down);
    tap(&mut engine, activate);
    capture(&engine, &directory.join("watch.ppm"))?;
    tap(&mut engine, back);
    tap(&mut engine, down);
    tap(&mut engine, activate);
    capture(&engine, &directory.join("play.ppm"))?;
    println!("Saved actual 64x32 menu frames to {}", directory.display());
    Ok(())
}
