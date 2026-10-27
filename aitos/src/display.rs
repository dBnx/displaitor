//! Board panel orientation and colour calibration, separate from DMA.
//!
//! The connected panel displays green/blue in reverse of the driver's RGB bus
//! order (confirmed by the 2026-10-19 test-card photo). Swap those channels only
//! at this physical adapter; applications, the simulator and protocol stay RGB.
use displaitor::{HEIGHT, WIDTH};
use embedded_graphics::{
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
};

pub struct PanelTarget<'a, D>(pub &'a mut D);
impl<D> OriginDimensions for PanelTarget<'_, D> {
    fn size(&self) -> Size {
        Size::new(WIDTH, HEIGHT)
    }
}
impl<D: DrawTarget<Color = Rgb888>> DrawTarget for PanelTarget<'_, D> {
    type Color = Rgb565;
    type Error = D::Error;
    fn draw_iter<I>(&mut self, pixels: I) -> Result<(), Self::Error>
    where
        I: IntoIterator<Item = Pixel<Rgb565>>,
    {
        let mapped = pixels
            .into_iter()
            .filter(|Pixel(p, _)| p.x >= 0 && p.y >= 0 && p.x < WIDTH as i32 && p.y < HEIGHT as i32)
            .map(|Pixel(p, c)| {
                let rgb = Rgb888::from(c);
                Pixel(
                    Point::new(WIDTH as i32 - 1 - p.x, HEIGHT as i32 - 1 - p.y),
                    Rgb888::new(rgb.r(), rgb.b(), rgb.g()),
                )
            });
        self.0.draw_iter(mapped)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use embedded_graphics::mock_display::MockDisplay;
    #[test]
    fn corners_rotate_and_offscreen_pixels_are_clipped() {
        let mut target = MockDisplay::new();
        PanelTarget(&mut target)
            .draw_iter([
                Pixel(Point::new(0, 0), Rgb565::RED),
                Pixel(Point::new(63, 31), Rgb565::BLUE),
                Pixel(Point::new(-1, 0), Rgb565::WHITE),
                Pixel(Point::new(64, 32), Rgb565::WHITE),
            ])
            .unwrap();
        assert_eq!(target.get_pixel(Point::new(63, 31)), Some(Rgb888::RED));
        assert_eq!(target.get_pixel(Point::new(0, 0)), Some(Rgb888::GREEN));
    }

    #[test]
    fn panel_rbg_calibration_maps_primary_and_secondary_colours() {
        let cases = [
            (Rgb565::RED, Rgb888::RED),
            (Rgb565::GREEN, Rgb888::BLUE),
            (Rgb565::BLUE, Rgb888::GREEN),
            (Rgb565::YELLOW, Rgb888::MAGENTA),
            (Rgb565::MAGENTA, Rgb888::YELLOW),
            (Rgb565::CYAN, Rgb888::CYAN),
            (Rgb565::WHITE, Rgb888::WHITE),
            (Rgb565::BLACK, Rgb888::BLACK),
        ];
        let mut target = MockDisplay::new();
        PanelTarget(&mut target)
            .draw_iter(
                cases
                    .iter()
                    .enumerate()
                    .map(|(x, (input, _))| Pixel(Point::new(x as i32, 0), *input)),
            )
            .unwrap();
        for (x, (_, expected)) in cases.iter().enumerate() {
            assert_eq!(
                target.get_pixel(Point::new(63 - x as i32, 31)),
                Some(*expected)
            );
        }
    }
}
