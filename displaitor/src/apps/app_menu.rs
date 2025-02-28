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

use crate::{
    string_buffer::{self, FixedBuffer},
    trait_app::Color,
    App, Controls, KeyReleaseEvent,
};

pub struct MenuEntry<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    pub name: &'static str,
    pub app: Box<dyn App<Target = D, Color = C>>,
}

pub struct Menu<const MAX_ENTRIES: usize, D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    entries: [MenuEntry<D, C>; MAX_ENTRIES],
    selected_index: usize,
    active_index: Option<usize>,

    nav_up_request: KeyReleaseEvent,
    nav_down_request: KeyReleaseEvent,
    selection_request: KeyReleaseEvent,
    special_request: KeyReleaseEvent,
    close_request: KeyReleaseEvent,
}

impl<const MAX_ENTRIES: usize, D, C> Menu<MAX_ENTRIES, D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    pub fn new(entries: [MenuEntry<D, C>; MAX_ENTRIES]) -> Self {
        Self {
            entries,
            selected_index: 0,
            active_index: None,

            nav_up_request: KeyReleaseEvent::new(),
            nav_down_request: KeyReleaseEvent::new(),
            selection_request: KeyReleaseEvent::new(),
            special_request: KeyReleaseEvent::new(),
            close_request: KeyReleaseEvent::new(),
        }
    }

    pub fn pre_select_entry(&mut self, index: usize) -> bool {
        if index < MAX_ENTRIES {
            self.selected_index = index;
            self.active_index = Some(index);
            true
        } else {
            false
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

    /// Delegates the update call, if something is selected and returns `true`. If the
    /// call wasn't delegated, it returns `false`.
    fn update_process_active(&mut self, dt: i64, t: i64, controls: &Controls) -> Option<bool> {
        if let Some(active_index) = self.active_index {
            let active_app = &mut self.entries[active_index];
            if !active_app.app.close_request() {
                return Some(active_app.app.update(dt, t, controls));
            }

            // info!("App {} requested closure", active_app.name);
            active_app.app.teardown();
            self.active_index = None;
        }

        None
    }

    fn update_process_menu_movement(&mut self, controls: &Controls) {
        if self.nav_down_request.fired() {
            self.select_next();
        } else if self.nav_up_request.fired() {
            self.select_previous();
        } else if self.selection_request.fired() {
            self.active_index = Some(self.selected_index);
            self.entries[self.selected_index].app.reset_state();
        }
    }
}

impl<const MAX_ENTRIES: usize, D, C> App for Menu<MAX_ENTRIES, D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        self.active_index = None;
        self.selected_index = 0;
        self.nav_up_request.reset();
        self.nav_down_request.reset();
        self.selection_request.reset();
        self.special_request.reset();
        self.close_request.reset();
    }

    fn update(&mut self, dt: i64, t: i64, controls: &Controls) -> bool {
        if let Some(update) = self.update_process_active(dt, t, controls) {
            return update;
        }

        // We are in the menu itself and don't delegate the call!
        self.nav_up_request.update(controls.dpad_up);
        self.nav_down_request.update(controls.dpad_down);
        self.selection_request.update(controls.buttons_a);
        self.special_request.update(controls.buttons_s);
        self.close_request.update(controls.buttons_b);

        self.update_process_menu_movement(controls);
        true
    }

    fn render(&self, target: &mut D) {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.render(target);
            return;
        }

        let text_style = MonoTextStyle::new(&FONT_6X10, C::WHITE);
        let text_style_active = MonoTextStyle::new(&FONT_6X10, C::MAGENTA);
        let mut buffer = FixedBuffer::<32>::new();
        for (i, entry) in self.entries.iter().enumerate() {
            buffer.clear();

            let y_offset = i as i32 * 11;
            let (prefix, style) = if i == self.selected_index {
                ("> ", text_style_active)
            } else {
                ("  ", text_style)
            };

            let _ = write!(buffer, "{}{}", prefix, entry.name);
            let _entry_text = Text::with_baseline(
                buffer.as_str(),
                Point::new(0, y_offset),
                style,
                Baseline::Top,
            )
            .draw(target);
        }

        if self.special_request.fired() {
            // Remove this
            let _special_test = Text::with_baseline(
                "SPECIAL!",
                Point::new(2, 10),
                text_style_active,
                Baseline::Top,
            )
            .draw(target);
        }
    }

    fn teardown(&mut self) {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.teardown();
        } else {
            // println!("Menu closed!");
        }
    }

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}
