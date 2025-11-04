use core::fmt::Write;

use embedded_graphics::{
    mono_font::{ascii::FONT_6X10, MonoTextStyle},
    prelude::*,
    text::{Baseline, Text},
};

use crate::{
    string_buffer::{self, FixedBuffer},
    trait_app::{Color, RenderStatus, UpdateResult},
    App, AppEnum, Controls, KeyReleaseEvent,
};

pub struct MenuEntry<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    pub name: &'static str,
    pub app: AppEnum<D, C>,
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

    fn count_valid_entries(&self) -> usize {
        self.entries.iter().take_while(|e| !e.name.is_empty()).count()
    }

    fn select_next(&mut self) {
        let valid_count = self.count_valid_entries();
        if valid_count == 0 {
            return;
        }
        self.selected_index = (self.selected_index + 1) % valid_count;
    }

    fn select_previous(&mut self) {
        let valid_count = self.count_valid_entries();
        if valid_count == 0 {
            return;
        }
        self.selected_index = if self.selected_index == 0 {
            valid_count - 1
        } else {
            self.selected_index - 1
        };
    }

    /// Delegates the update call, if something is selected and returns `true`. If the
    /// call wasn't delegated, it returns `false`.
    fn update_process_active(&mut self, dt: i64, t: i64, controls: &Controls) -> Option<UpdateResult> {
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

    fn update(&mut self, dt: i64, t: i64, controls: &Controls) -> UpdateResult {
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
        RenderStatus::VisibleChange.into()
    }

    fn render(&self, target: &mut D) {
        if let Some(active_index) = self.active_index {
            self.entries[active_index].app.render(target);
            return;
        }

        let text_style = MonoTextStyle::new(&FONT_6X10, C::WHITE);
        let text_style_active = MonoTextStyle::new(&FONT_6X10, C::MAGENTA);
        let mut buffer = FixedBuffer::<32>::new();
        let mut display_index = 0;
        for (i, entry) in self.entries.iter().enumerate() {
            if entry.name.is_empty() {
                continue;
            }
            buffer.clear();

            let y_offset = display_index as i32 * 11;
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
            display_index += 1;
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
