use crate::trait_app::Color;
use crate::{App, Controls};
use core::marker::PhantomData;
use embedded_graphics::geometry::Point;
use embedded_graphics::mono_font::{ascii::FONT_6X10, MonoTextStyle};
use embedded_graphics::prelude::*;
use embedded_graphics::text::{Baseline, Text};

// Mockup for the random function
mod random {
    pub const fn random<const N: usize>() -> usize {
        N % 7 // Placeholder, replace with actual randomness
    }
}

pub struct ScrollingText<D, C, const N: usize>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    messages: [&'static str; N],
    index_current: usize,
    index_next: usize,

    line_buffer: [char; 32*2], // TODO: Make 32 (width) a const generic 
    line_buffer_offset: usize,

    // offset_next: i32,
    // velocity: i32,
    _marker: PhantomData<D>,
}

impl<D, C, const N: usize> ScrollingText<D, C, N>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    pub const fn new(messages: [&'static str; N]) -> Self {
        Self {
            messages,
            index_current: random::random::<N>(),
            index_next: random::random::<N>(),

            line_buffer: [' '; 32*2],
            line_buffer_offset: 0,

            _marker: PhantomData,
        }
    }
}

impl<D, C, const N: usize> App for ScrollingText<D, C, N>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        // self.index_current = random::random::<N>();
    }

    fn update(&mut self, dt_us: i64, _t_us: i64, _controls: &Controls) {
        self.offset -= self.velocity * (dt_us as i32 / 100_000);

        if self.offset < -((self.messages[self.current_index].len() as i32) * 6) {
            self.current_index = random::random::<N>();
            self.offset = 32; // Reset position to screen width
        }
    }

    fn render(&mut self, target: &mut Self::Target) {
        let text_style = MonoTextStyle::new(&FONT_6X10, C::WHITE);
        let text = self.messages[self.current_index];

        let _ = Text::with_baseline(text, Point::new(self.offset, 10), text_style, Baseline::Top)
            .draw(target);
    }

    fn close_request(&self) -> bool {
        false
    }
}
