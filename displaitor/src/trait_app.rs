use embedded_graphics::{
    pixelcolor::Rgb565, prelude::*
};

use crate::Controls;

// TODO: update should return bool, if an update occured and render must be called. Otherwise
// we could avoid re-rendering the frame.

pub trait App
{
    type Target: DrawTarget;
    type Color: PixelColor + RgbColor;

    // TODO: We should be able to re-init the App state.
    fn setup(&mut self) {}

    fn update(&mut self, dt: i64, t: i64, controls: &Controls);

    fn render(&mut self, target: &mut Self::Target);

    fn teardown(&mut self) {}
    
    /// If `true` is returned, the application wants to be closed. Calls to `render` and `update` can still happen for some time after
    /// requesting closure.
    fn close_request(&self) -> bool { false }
}
