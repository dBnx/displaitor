use core::convert::Infallible;
use displaitor::{HEIGHT, WIDTH};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

pub struct Framebuffer {
    pixels: Vec<Rgb565>,
}

impl Framebuffer {
    pub fn new() -> Self {
        Self {
            pixels: vec![Rgb565::BLACK; (WIDTH * HEIGHT) as usize],
        }
    }

    pub fn checksum(&self) -> u64 {
        self.pixels
            .iter()
            .fold(0xcbf2_9ce4_8422_2325, |hash, pixel| {
                (hash ^ u64::from(pixel.into_storage())).wrapping_mul(0x0000_0100_0000_01b3)
            })
    }

    pub fn has_visible_pixels(&self) -> bool {
        self.pixels.iter().any(|pixel| *pixel != Rgb565::BLACK)
    }
    pub fn write_ppm(&self, path: &str) -> Result<(), String> {
        use embedded_graphics::pixelcolor::Rgb888;
        use std::io::Write;
        let mut file = std::fs::File::create(path).map_err(|e| e.to_string())?;
        write!(file, "P6\n{WIDTH} {HEIGHT}\n255\n").map_err(|e| e.to_string())?;
        for pixel in &self.pixels {
            let pixel = Rgb888::from(*pixel);
            file.write_all(&[pixel.r(), pixel.g(), pixel.b()])
                .map_err(|e| e.to_string())?;
        }
        Ok(())
    }

    #[cfg(feature = "sdl")]
    pub fn rgb_bytes(&self, output: &mut [u8]) {
        use embedded_graphics::pixelcolor::Rgb888;
        for (pixel, bytes) in self.pixels.iter().zip(output.as_chunks_mut::<3>().0) {
            let pixel = Rgb888::from(*pixel);
            bytes.copy_from_slice(&[pixel.r(), pixel.g(), pixel.b()]);
        }
    }
}

impl OriginDimensions for Framebuffer {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}

impl DrawTarget for Framebuffer {
    type Color = Rgb565;
    type Error = Infallible;

    fn draw_iter<I>(&mut self, pixels: I) -> Result<(), Self::Error>
    where
        I: IntoIterator<Item = Pixel<Self::Color>>,
    {
        for Pixel(point, color) in pixels {
            if point.x >= 0 && point.y >= 0 && point.x < WIDTH as i32 && point.y < HEIGHT as i32 {
                self.pixels[(point.y as u32 * WIDTH + point.x as u32) as usize] = color;
            }
        }
        Ok(())
    }

    fn clear(&mut self, color: Self::Color) -> Result<(), Self::Error> {
        self.pixels.fill(color);
        Ok(())
    }
}
