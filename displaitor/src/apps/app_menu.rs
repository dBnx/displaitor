use core::fmt::Write;

use alloc::boxed::Box;
/// struct DummyApp {
///     id: u32,
/// }
/// 
/// impl App for DummyApp {
///     fn update(&mut self, _dt: i64, _t: i64, _controls: &Controls) {
///         println!("DummyApp {} is running!", self.id);
///     }
///     fn render<D, C>(&mut self, _target: &mut D)
///     where
///         D: DrawTarget<Color = C>,
///         C: PixelColor,
///     {
///         println!("Rendering DummyApp {}", self.id);
///     }
/// }
/// 
/// fn main() {
///     let mut app1 = DummyApp { id: 1 };
///     let mut app2 = DummyApp { id: 2 };
/// 
///     let mut menu: Menu<2, DummyApp> = Menu::new();
///     menu.add_entry("App 1", app1).unwrap();
///     menu.add_entry("App 2", app2).unwrap();
/// 
///     let mut controls = Controls {
///         buttons_a: false,
///         buttons_b: false,
///         dpad_up: false,
///         dpad_down: true,
///         dpad_left: false,
///         dpad_right: false,
///     };
/// 
///     menu.update(0, 0, &controls); // Navigate down
///     menu.render::<_, Rgb565>(&mut DummyTarget); // Render menu
/// }


use embedded_graphics::{
    mono_font::{ascii::FONT_6X10, MonoTextStyle},
    prelude::*,
    text::{Baseline, Text},
};

use crate::{string_buffer, App, Controls};

pub struct MenuEntry<D, C> 
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub name: &'static str,
    pub app: Box<dyn App<Target=D, Color=C>>,
}

pub struct Menu<const MAX_ENTRIES: usize, D, C> 
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    entries: [MenuEntry<D, C>; MAX_ENTRIES],
    selected_index: usize,
    active_index: Option<usize>,
}

impl<const MAX_ENTRIES: usize, D, C> Menu<MAX_ENTRIES, D, C> 
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub fn new(entries: [MenuEntry<D, C>; MAX_ENTRIES]) -> Self {
        Self {
            entries,
            selected_index: 0,
            active_index: None,
        }
    }

    fn select_next(&mut self) {
        self.selected_index = (self.selected_index + 1) % MAX_ENTRIES;
    }

    fn select_previous(&mut self) {
        self.selected_index = if self.selected_index == 0 {
            MAX_ENTRIES - 1
        } else {
            self.selected_index - 1
        };
    }
}

impl<const MAX_ENTRIES: usize, D, C> App for Menu<MAX_ENTRIES, D, C> 
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    type Target = D;
    type Color = C;

    fn update(&mut self, dt: i64, t: i64, controls: &Controls) {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.update(dt, t, controls);
            return;
        }

        if controls.dpad_down {
            self.select_next();
        } else if controls.dpad_up {
            self.select_previous();
        } else if controls.buttons_a {
            self.active_index = Some(self.selected_index);
            // TODO: Re-setup?
            // self.entries[self.selected_index].setup();
        }
    }

    fn render(&mut self, target: &mut D)
    where
        D: DrawTarget<Color = C>,
        C: PixelColor + RgbColor,
    {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.render(target);
            return;
        }

        let text_style = MonoTextStyle::new(&FONT_6X10, C::WHITE);
        let mut buffer = string_buffer::get_global_buffer();
        for (i, entry) in self.entries.iter().enumerate() {
            buffer.clear();

            let y_offset = i as i32 * 12; // Adjust spacing
            let prefix = if i == self.selected_index { "> " } else { "  " };
            let _ = write!(buffer, "{}{}", prefix, entry.name);
            let _entry_text = Text::with_baseline(buffer.as_str(), Point::new(0, y_offset), text_style, Baseline::Top)
                .draw(target);
        }
    }

    fn teardown(&mut self) {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.teardown();
        } else {
            // println!("Menu closed!");
            todo!("Menu closed!");
        }
    }

    fn close_request(&self) -> bool {
        todo!()
    }
}
