use core::marker::PhantomData;

use embedded_graphics::{
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
};
use heapless::Vec;

use crate::{
    trait_app::{Color, RenderStatus, UpdateResult},
    App, Controls,
};

#[derive(Clone, PartialEq, Debug)]
pub struct Dummy<D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    _marker: PhantomData<D>,
}

impl<D, C> Dummy<D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub fn new() -> Self {
        Self {
            _marker: Default::default(),
        }
    }
}

impl<D, C> App for Dummy<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {}

    fn update(&mut self, dt: i64, _t: i64, controls: &Controls) -> UpdateResult {
        RenderStatus::VisibleChange.into()
    }

    fn render(&self, target: &mut Self::Target) {}

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        true
    }
}
