//! Export the actual empty-Canvas setup screen without hardware.
use displaitor::{HEIGHT, WIDTH, canvas::Canvas};
use embedded_graphics::{
    mock_display::MockDisplay,
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
};
use std::{fs, path::Path};

fn main() -> std::io::Result<()> {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "target/canvas-setup.ppm".into());
    let path = Path::new(&path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut frame = MockDisplay::<Rgb565>::new();
    frame.set_allow_overdraw(true);
    Canvas::new().render(&mut frame).unwrap();
    let mut bytes = format!("P6\n{WIDTH} {HEIGHT}\n255\n").into_bytes();
    for y in 0..HEIGHT as i32 {
        for x in 0..WIDTH as i32 {
            let color = Rgb888::from(frame.get_pixel(Point::new(x, y)).unwrap_or(Rgb565::BLACK));
            bytes.extend_from_slice(&[color.r(), color.g(), color.b()]);
        }
    }
    fs::write(path, bytes)
}
