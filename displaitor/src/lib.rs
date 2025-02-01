#![allow(unused)]
#![no_std]

#[macro_use]
extern crate alloc;

mod controls;
pub mod string_buffer;
mod trait_app;

use alloc::boxed::Box;
use apps::Menu;
pub use controls::Controls;
use embedded_graphics::prelude::{DrawTarget, PixelColor, RgbColor};
pub use trait_app::App;

pub mod apps {
    mod app_dummy;
    mod app_menu;
    mod app_names;
    pub use app_dummy::Dummy;
    pub use app_menu::{Menu, MenuEntry};
    pub use app_names::Names;
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

pub fn main_app<D, C>() -> impl App<Target = D, Color = C>
where
    D: DrawTarget<Color = C> + 'static,
    C: PixelColor + RgbColor + 'static
{
    apps::Menu::new([
        apps::MenuEntry {
            name: "Pong",
            app: Box::new(games::Pong::<D, C>::new(64, 32)),
        },
        apps::MenuEntry {
            name: "Snake",
            app: Box::new(games::Snake::<64, 32, 32, D, C>::new()),
        },
        apps::MenuEntry {
            name: "Nyancat",
            app: Box::new(games::Pong::<D, C>::new(64, 32)),
        },
    ])
}

/*
pub struct MainApp<'a, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub(crate) menu: apps::Menu<'a, 3, D, C>,
    pub(crate) app1: games::Pong<D, C>,
    pub(crate) app2: games::Snake<64, 32, 32, D, C>,
    pub(crate) app3: games::Pong<D, C>,
}

impl<'a, D, C> MainApp<'a, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    fn new() -> Self {
        let mut a = apps::Dummy::new();
        let mut b = apps::Dummy::new();
        let mut c = apps::Dummy::new();
        let dummy_menu = Menu::new([
            apps::MenuEntry {
                name: "-",
                app: &mut a,
            },
            apps::MenuEntry {
                name: "-",
                app: &mut b,
            },
            apps::MenuEntry {
                name: "-",
                app: &mut c,
            },
        ]);

        let main_app = MainApp {
            app1: games::Pong::new(64, 32),
            app2: games::Snake::new(),
            app3: games::Pong::new(64, 32),
            menu: dummy_menu,
        };

        main_app.menu = apps::Menu::new([
            apps::MenuEntry {
                name: "Pong",
                app: &mut main_app.app1,
            },
            apps::MenuEntry {
                name: "Snake",
                app: &mut main_app.app2,
            },
            apps::MenuEntry {
                name: "Nyancat",
                app: &mut main_app.app3,
            },
        ]);

        main_app
    }
} */

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
