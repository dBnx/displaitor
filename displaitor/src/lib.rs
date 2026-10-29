//! Hardware-independent, allocation-free application for the 64×32 Displaitor.
//!
//! Adapters sample logical pressed controls, call [`Engine::update`] with elapsed
//! monotonic time, then draw when [`Update::redraw`] is set. Rendering and audio
//! output errors remain the adapter's responsibility.
#![no_std]
#![forbid(unsafe_code)]

mod audio;
pub mod canvas;
pub mod canvas_input;
pub mod canvas_protocol;
mod content;
mod cozy;
mod engine;
mod games;
mod input;
pub mod menu_view;
pub mod navigation;
mod render;

pub use audio::AudioId;
pub use engine::{AppId, DEFAULT_MENU_COUNT, Engine, Screen, Update};
pub use input::Controls;

pub const WIDTH: u32 = 64;
pub const HEIGHT: u32 = 32;
