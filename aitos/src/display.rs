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

/// Native scenes use logical colours. Canvas pixels already carry host gamma.
pub struct PanelTarget<'a, D> {
    target: &'a mut D,
    native: bool,
}
impl<'a, D> PanelTarget<'a, D> {
    pub fn native(target: &'a mut D) -> Self {
        Self {
            target,
            native: true,
        }
    }
    pub fn canvas(target: &'a mut D) -> Self {
        Self {
            target,
            native: false,
        }
    }
}

// Gamma 2.8, rounded in the original RGB565 channel domain, matching Python's
// OutputGamma. No floating point, heap or full-frame intermediate on the MCU.
const GAMMA5: [u8; 32] = [
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 15, 17, 19, 21, 23,
    26, 28, 31,
];
const GAMMA6: [u8; 64] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 7, 8, 9,
    9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 22, 23, 25, 26, 28, 29, 31, 33, 35, 37, 39, 41, 43,
    45, 48, 50, 52, 55, 58, 60, 63,
];

fn calibrated(color: Rgb565) -> Rgb565 {
    Rgb565::new(
        GAMMA5[color.r() as usize],
        GAMMA6[color.g() as usize],
        GAMMA5[color.b() as usize],
    )
}
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
                let rgb = Rgb888::from(if self.native { calibrated(c) } else { c });
                Pixel(
                    Point::new(WIDTH as i32 - 1 - p.x, HEIGHT as i32 - 1 - p.y),
                    Rgb888::new(rgb.r(), rgb.b(), rgb.g()),
                )
            });
        self.target.draw_iter(mapped)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use embedded_graphics::mock_display::MockDisplay;
    #[test]
    fn corners_rotate_and_offscreen_pixels_are_clipped() {
        let mut target = MockDisplay::new();
        PanelTarget::native(&mut target)
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
        PanelTarget::native(&mut target)
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

#[cfg(test)]
mod gamma_tests {
    use super::*;
    use embedded_graphics::mock_display::MockDisplay;

    #[test]
    fn native_midtone_is_corrected_and_canvas_is_not_corrected_twice() {
        let logical = Rgb565::new(16, 32, 16);
        let corrected = Rgb565::new(5, 9, 5);
        assert_eq!(calibrated(logical), corrected);
        let mut native = MockDisplay::new();
        let mut canvas = MockDisplay::new();
        PanelTarget::native(&mut native)
            .draw_iter([Pixel(Point::zero(), logical)])
            .unwrap();
        PanelTarget::canvas(&mut canvas)
            .draw_iter([Pixel(Point::zero(), corrected)])
            .unwrap();
        assert_eq!(native, canvas);
    }

    #[test]
    fn all_channel_values_follow_gamma_2_8_with_preserved_endpoints() {
        for (bits, table) in [(5, GAMMA5.as_slice()), (6, GAMMA6.as_slice())] {
            let maximum = ((1u32 << bits) - 1) as f64;
            for (value, &actual) in table.iter().enumerate() {
                let expected = ((value as f64 / maximum).powf(2.8) * maximum).round() as u8;
                assert_eq!(actual, expected);
            }
            assert_eq!(table[0], 0);
            assert_eq!(table[table.len() - 1], maximum as u8);
            assert!(table.windows(2).all(|pair| pair[0] <= pair[1]));
        }
    }
}
