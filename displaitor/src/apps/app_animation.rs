/// Just dispalys an image
use core::{marker::PhantomData, mem::MaybeUninit};

use embedded_error_chain::ChainError;
use embedded_graphics::{
    draw_target::ColorConverted,
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
};
use heapless::Vec;
use tinyqoi::Qoi;

use crate::{trait_app::Color, App, Controls, KeyReleaseEvent};

pub struct Animation<D, C, const N: usize>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    images: [Qoi<'static>; N],
    current_frame_index: usize,
    current_frame_time: i64,

    close_request: KeyReleaseEvent,
    _marker: PhantomData<D>,
}

impl<D, C, const N: usize> Animation<D, C, N>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub fn new(qoi_data: [&'static [u8]; N]) -> Self {
        let images = qoi_data.map(|data| Qoi::new(data).expect("Invalid QOI data"));

        Self {
            images,
            current_frame_index: 0,
            current_frame_time: 0,

            close_request: KeyReleaseEvent::new(),
            _marker: Default::default(),
        }
    }
}

impl<D, C, const N: usize> App for Animation<D, C, N>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        self.current_frame_index = 0;
        self.current_frame_time = 0;
        self.close_request.reset();
    }

    fn update(&mut self, dt: i64, t: i64, controls: &Controls) {
        self.close_request.update(controls.buttons_b);

        if t - self.current_frame_time > 50_000 {
            self.current_frame_time = t;
            self.current_frame_index += 1;
            self.current_frame_index %= N;
        }
    }

    fn render(&mut self, target: &mut Self::Target) {
        let mut target_rgb888: ColorConverted<'_, _, Rgb888> = target.color_converted();

        let current_frame = &self.images[self.current_frame_index];
        let _img = embedded_graphics::image::Image::new(current_frame, Point::zero())
            .draw(&mut target_rgb888);
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}
