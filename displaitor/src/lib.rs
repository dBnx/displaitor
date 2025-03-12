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
use apps::Menu;
pub use controls::Controls;
use embedded_graphics::prelude::{DrawTarget, PixelColor, RgbColor};
pub(crate) use key_release::KeyReleaseEvent;
use trait_app::Color;
pub use trait_app::{App, AudioID};

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
            name: "Nyankatz",
            app: Box::new(apps::Animation::new(
                [
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
                ],
                AudioID::MusicNyan,
            )),
        },
        apps::MenuEntry {
            name: "Hyper!",
            app: Box::new(apps::Animation::new(
                [
                    include_bytes!("../assets/hyperspace/0001.qoi"),
                    include_bytes!("../assets/hyperspace/0002.qoi"),
                    include_bytes!("../assets/hyperspace/0003.qoi"),
                    include_bytes!("../assets/hyperspace/0004.qoi"),
                    include_bytes!("../assets/hyperspace/0005.qoi"),
                    include_bytes!("../assets/hyperspace/0006.qoi"),
                    include_bytes!("../assets/hyperspace/0007.qoi"),
                    include_bytes!("../assets/hyperspace/0008.qoi"),
                    include_bytes!("../assets/hyperspace/0009.qoi"),
                    include_bytes!("../assets/hyperspace/0010.qoi"),
                    include_bytes!("../assets/hyperspace/0011.qoi"),
                    include_bytes!("../assets/hyperspace/0012.qoi"),
                    include_bytes!("../assets/hyperspace/0013.qoi"),
                    include_bytes!("../assets/hyperspace/0014.qoi"),
                ],
                AudioID::Stop,
            )),
        },
        apps::MenuEntry {
            name: "A break",
            app: Box::new(apps::Animation::new(
                [
                    include_bytes!("../assets/fire2/0001.qoi"),
                    include_bytes!("../assets/fire2/0002.qoi"),
                    include_bytes!("../assets/fire2/0003.qoi"),
                    include_bytes!("../assets/fire2/0004.qoi"),
                ],
                AudioID::Stop,
            )),
        }, 
        //  TODO: With love 
        //  - Pati, Elena, Manuel, David
    ]);

    let scrolling: apps::ScrollingText<D, C, _> =
        apps::ScrollingText::new(const_str::split!(include_str!("../assets/names.txt"), "\n"));

    let mut m = apps::Menu::new([
        apps::MenuEntry {
            name: "<3",
            app: Box::new(scrolling),
        },
        apps::MenuEntry {
            name: "Imageine",
            app: Box::new(animation_menu),
        },
        apps::MenuEntry {
            name: "Games",
            app: Box::new(games_menu),
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
