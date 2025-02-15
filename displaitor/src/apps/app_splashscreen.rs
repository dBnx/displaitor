/// Just dispalys an image
use core::marker::PhantomData;

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

pub struct SplashScreen<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    image: [Qoi<'static>; 2], // TODO: Make N generic
    close_request: KeyReleaseEvent,
    /// Automatically close after this time
    close_after_us: i64,
    last_time_us: i64,
    current_frame: usize,
    time_over: bool,
    _marker: PhantomData<D>,
}

impl<D, C> SplashScreen<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    // TODO: Should take a const filepath of a .qoi
    pub fn new(qoi_data: [&'static [u8]; 2]) -> Self {
        Self {
            image: [
                Qoi::new(qoi_data[0]).unwrap(),
                Qoi::new(qoi_data[1]).unwrap(),
            ],

            close_request: KeyReleaseEvent::new(),
            close_after_us: 4_000_000,
            last_time_us: 0,
            current_frame: 0,
            time_over: false,

            _marker: Default::default(),
        }
    }
}

impl<D, C> App for SplashScreen<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        self.close_request.reset();
        self.current_frame = 0;
        self.time_over = false;
    }

    fn update(&mut self, dt: i64, t_us: i64, controls: &Controls) {
        self.close_request.update(controls.buttons_b);
        self.last_time_us = t_us;
        self.current_frame = if t_us < self.close_after_us / 2 { 0 } else { 1 };
        if t_us > self.close_after_us {
            self.time_over = true;
        }
    }

    fn render(&mut self, target: &mut Self::Target) {
        let mut target_rgb888: ColorConverted<'_, _, Rgb888> = target.color_converted();


        let image = &self.image[self.current_frame];
        let _img = embedded_graphics::image::Image::with_center(image, Point::new(32,16))
            .draw(&mut target_rgb888);
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.time_over || self.close_request.fired()
    }
}
