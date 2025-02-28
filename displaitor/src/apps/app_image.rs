/// Just displays an image
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

use crate::{trait_app::{Color, RenderStatus, UpdateResult}, App, Controls, KeyReleaseEvent};

#[derive(PartialEq, Debug)]
pub struct Image<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    image: Qoi<'static>,
    close_request: KeyReleaseEvent,
    _marker: PhantomData<D>,
}

impl<D, C> Image<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    // TODO: Should take a const filepath of a .qoi
    pub fn new(qoi_data: &'static [u8]) -> Self {
        Self {
            image: Qoi::new(qoi_data).unwrap(),
            close_request: KeyReleaseEvent::new(),
            _marker: Default::default(),
        }
    }
}

impl<D, C> App for Image<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        self.close_request.reset();
    }

    fn update(&mut self, dt: i64, _t: i64, controls: &Controls) -> UpdateResult {
        self.close_request.update(controls.buttons_b);
        RenderStatus::VisibleChange.into() // TODO: false after the first time
    }

    fn render(&self, target: &mut Self::Target) {
        let mut target_rgb888: ColorConverted<'_, _, Rgb888> = target.color_converted();

        let _img = embedded_graphics::image::Image::new(&self.image, Point::zero())
            .draw(&mut target_rgb888);
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}
