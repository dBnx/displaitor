#![allow(unused)]
#![no_std]
#![feature(iter_collect_into)]
#![feature(generic_arg_infer)]

#[macro_use]
extern crate alloc;

mod controls;
mod key_release;
pub mod string_buffer;
mod trait_app;

use alloc::boxed::Box;
use apps::{Menu};
pub use controls::Controls;
use embedded_graphics::prelude::{DrawTarget, PixelColor, RgbColor};
pub(crate) use key_release::KeyReleaseEvent;
pub use trait_app::App;
use trait_app::Color;

// Replace with a mod.rs ?
pub mod apps {
    mod app_animation;
    mod app_dummy;
    mod app_image;
    mod app_menu;
    mod app_scrolling_text;
    mod app_splashscreen;
    pub use app_animation::Animation;
    pub use app_dummy::Dummy;
    pub use app_image::Image;
    pub use app_menu::{Menu, MenuEntry};
    pub use app_scrolling_text::ScrollingText;
    pub use app_splashscreen::SplashScreen;
}

pub mod games {
    mod app_gameboy;
    mod app_pong;
    mod app_snake;
    mod app_space_invader;
    pub use app_gameboy::GameBoy;
    pub use app_pong::Pong;
    pub use app_snake::Snake;
    pub use app_space_invader::SpaceInvader;
}

pub fn startup_app<'a, D, C>() -> impl App<Target = D, Color = C>
where
    D: DrawTarget<Color = C> + 'static,
    // C: PixelColor + RgbColor + 'static
    C: Color + 'static,
{
    apps::SplashScreen::new([
        include_bytes!("../assets/MicroRascon.qoi"),
        include_bytes!("../assets/MicroRascon_Text.qoi"),
    ])
}

pub fn main_app<'a, D, C>() -> impl App<Target = D, Color = C>
where
    D: DrawTarget<Color = C> + 'static,
    // C: PixelColor + RgbColor + 'static
    C: Color + 'static,
{
    let games_menu = apps::Menu::new([
        apps::MenuEntry {
            name: "Pong",
            app: Box::new(games::Pong::<D, C>::new(64, 32)),
        },
        apps::MenuEntry {
            name: "Schnek",
            app: Box::new(games::Snake::<64, 32, 32, D, C>::new()),
        },
    ]);
    let animation_menu = apps::Menu::new([
        apps::MenuEntry {
            name: "Ferd",
            app: Box::new(apps::Image::<D, C>::new(include_bytes!(
                "../assets/Ferd.qoi"
            ))),
        },
        apps::MenuEntry {
            name: "Battle Bull",
            app: Box::new(apps::Image::new(include_bytes!(
                "../assets/Battle Bull.qoi"
            ))),
        },
        apps::MenuEntry {
            name: "Nyankatz",
            app: Box::new(apps::Animation::new([
                include_bytes!("../assets/nyan/01.qoi"),
                include_bytes!("../assets/nyan/02.qoi"),
                include_bytes!("../assets/nyan/03.qoi"),
                include_bytes!("../assets/nyan/04.qoi"),
                include_bytes!("../assets/nyan/05.qoi"),
                include_bytes!("../assets/nyan/06.qoi"),
                include_bytes!("../assets/nyan/07.qoi"),
                include_bytes!("../assets/nyan/08.qoi"),
                include_bytes!("../assets/nyan/09.qoi"),
                include_bytes!("../assets/nyan/10.qoi"),
                include_bytes!("../assets/nyan/11.qoi"),
                include_bytes!("../assets/nyan/12.qoi"),
            ])),
        },
    ]);

    let scrolling: apps::ScrollingText<D, C, _> = apps::ScrollingText::new(const_str::split!(include_str!("../assets/names.txt"), "\n"));

    let mut m = apps::Menu::new([
        apps::MenuEntry {
            name: "<3",
            app: Box::new(scrolling),
        },
        apps::MenuEntry {
            name: "Games",
            app: Box::new(games_menu),
        },
        apps::MenuEntry {
            name: "Imagine!",
            app: Box::new(animation_menu),
        },
    ]);
    let _ = m.pre_select_entry(0);
    m
}

fn add(left: u64, right: u64) -> u64 {
    left + right
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn it_works() {
        let result = add(2, 2);
        assert_eq!(result, 4);
    }
}
