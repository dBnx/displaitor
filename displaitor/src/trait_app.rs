use embedded_graphics::{
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
};

use crate::Controls;

pub trait Color: PixelColor + RgbColor + WebColors + From<Rgb888> + Clone {}

impl Color for Rgb565 {}

// TODO: Move to separate crate in workspace
pub enum AudioID {
    BootUp,
    Ping,
    Pong,
    Nom,
    GameOver,
    MusicDepp,
    MusicTetris,
    MusicPen,
}

#[derive(PartialEq)]
pub enum RenderStatus {
    VisibleChange,
    NoVisibleChange,
}

pub struct UpdateResult {
    pub(crate) render_result: RenderStatus,
    pub(crate) audio_queue_request: Option<AudioID>,
}

impl Into<UpdateResult> for RenderStatus {
    fn into(self) -> UpdateResult {
        UpdateResult {
            render_result: self,
            audio_queue_request: None,
        }
    }
}

impl UpdateResult {
    pub fn visible_changes(&self) -> bool {
        self.render_result == RenderStatus::VisibleChange
    }
}

pub type AppBoxed<D, C> = alloc::boxed::Box<dyn App<Target = D, Color = C>>;

pub trait App {
    type Target: DrawTarget;
    type Color: Color;

    /// Must always bring the app in a well-defined and re-usable state.
    fn reset_state(&mut self);

    /// Updates the internal state. `true` is returned, if the render would be different from the previous state.
    /// So `false` indicates, that the previous frame can be re-used.
    #[must_use = "Skipping a expensive draw call is mandatory on embedded"]
    fn update(&mut self, dt_us: i64, t_us: i64, controls: &Controls) -> UpdateResult;

    /// Draw the current state to the screen.
    fn render(&self, target: &mut Self::Target);

    /// Could be called at any time. It is guaranteed, that `reset_sate` is called called before the app is used again.
    fn teardown(&mut self) {}

    /// If `true` is returned, the application wants to be closed. Calls to `render` and `update` can still happen for some time after
    /// requesting closure.
    fn close_request(&self) -> bool {
        false
    }
}
