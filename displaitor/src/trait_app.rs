use embedded_graphics::{
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
};

use crate::Controls;

// TODO: update should return bool, if an update occured and render must be called. Otherwise
// we could avoid re-rendering the frame.

pub trait Color: PixelColor + RgbColor + WebColors + From<Rgb888> {}

impl Color for Rgb565 {}

pub trait App {
    type Target: DrawTarget;
    type Color: Color;

    // TODO: We should be able to re-init the App state.
    fn reset_state(&mut self);

    fn update(&mut self, dt_us: i64, t_us: i64, controls: &Controls);

    fn render(&mut self, target: &mut Self::Target);

    fn teardown(&mut self) {}

    /// If `true` is returned, the application wants to be closed. Calls to `render` and `update` can still happen for some time after
    /// requesting closure.
    fn close_request(&self) -> bool {
        false
    }
}
