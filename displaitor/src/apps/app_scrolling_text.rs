
use core::marker::PhantomData;
use embedded_graphics::prelude::*;
// use embedded_graphics::mono_font::{ascii::FONT_6X10, MonoTextStyle};
use embedded_graphics::mono_font::MonoTextStyle;
use embedded_graphics::text::{Baseline, Text};
use embedded_graphics::pixelcolor::{Rgb888, Rgb565};
use tinyrand::{Rand, StdRand, Seeded};
use crate::{App, Color, Controls, KeyReleaseEvent};

// NOTE: Font settings
// - FONT_6X10  Great if the top / bottom should also be used.
// - FONT_10X20
// use embedded_graphics::mono_font::ascii::FONT_10X20 as FONT;
use embedded_graphics::mono_font::iso_8859_10::FONT_10X20 as FONT;
const FONT_WIDTH: i32 = 10;
const FONT_VERT_OFFSET: i32 = 6;

/// A scrolling text application that continuously scrolls a random sentence followed immediately
/// by another random sentence. On every update call the text is shifted one pixel to the left.
/// When the current sentence fully scrolls off the screen the next message becomes current and
/// a new message is chosen randomly. Additionally, the color of each message is randomized.
pub struct ScrollingText<D, C, const N: usize>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    messages: [&'static str; N],
    index_current: usize,
    index_next: usize,
    /// The current horizontal offset (in pixels) for the current message.
    line_buffer_offset: usize,
    current_color: C,
    next_color: C,
    prng: StdRand,

    last_update: i64,
    close_request: KeyReleaseEvent,

    _marker: PhantomData<D>,
}

fn get_random_color<C: Color>(prng: &mut StdRand) -> C {
    C::from(Rgb888::new(
        (prng.next_u16() & 0xFF) as u8,
        (prng.next_u16() & 0xFF) as u8,
        (prng.next_u16() & 0xFF) as u8,
    ))
}

impl<D, C, const N: usize> ScrollingText<D, C, N>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    /// Create a new scrolling text app.
    ///
    /// - `messages` is a fixed-size array of sentences.
    /// - The PRNG is seeded with a fixed value (change as needed).
    /// - The current and next message indices (and colors) are chosen at random.
    pub fn new(messages: [&'static str; N]) -> Self {
        let mut prng = StdRand::seed(0xDEAD_BEEF); 
        let index_current = prng.next_lim_usize(N);
        let index_next = prng.next_lim_usize( N);
        // Generate random colors. We assume that rand() returns a u32.
        let current_color = get_random_color(&mut prng);
        let next_color = get_random_color(&mut prng);

        Self {
            messages,
            index_current,
            index_next,
            line_buffer_offset: 0,
            current_color,
            next_color,
            prng,

            last_update: 0,
            close_request: KeyReleaseEvent::new(),

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
        self.line_buffer_offset = 0;
        self.index_current = self.prng.next_lim_usize(N);
        self.index_next = self.prng.next_lim_usize(N);
        self.current_color = get_random_color(&mut self.prng);
        self.next_color = get_random_color(&mut self.prng);

        self.close_request.reset();
    }

    fn update(&mut self, _dt_us: i64, t_us: i64, controls: &Controls) {
        self.close_request.update(controls.buttons_b);

        // Time gate
        const MIN_UPDATE_DT_US: i64 = 30_000;
        if t_us - self.last_update < MIN_UPDATE_DT_US {
            return;
        }
        self.last_update = t_us;

        // Shift the text one pixel left per update.
        self.line_buffer_offset += 1;
        // Assume each character is 6 pixels wide.
        let current_message = self.messages[self.index_current];
        let current_width = current_message.len() as i32 * FONT_WIDTH;
        if self.line_buffer_offset as i32 >= current_width {
            // The current message has fully scrolled off.
            self.line_buffer_offset -= current_width as usize;
            // Make the next message current.
            self.index_current = self.index_next;
            self.current_color = self.next_color;
            // Choose a new next message and color.
            self.index_next = self.prng.next_lim_usize(N);
            self.next_color = get_random_color(&mut self.prng);
        }
    }

    fn render(&mut self, target: &mut Self::Target) {
        // Create text styles for current and next messages.
        let style_current = MonoTextStyle::new(&FONT, self.current_color);
        let style_next = MonoTextStyle::new(&FONT, self.next_color);
        let current = self.messages[self.index_current];
        let next = self.messages[self.index_next];
        // The current message is drawn shifted left by `line_buffer_offset` pixels.
        let x_offset = -(self.line_buffer_offset as i32);
        // Draw the current message.
        let _ = Text::with_baseline(current, Point::new(x_offset, FONT_VERT_OFFSET), style_current, Baseline::Top)
            .draw(target);
        // Compute the pixel width of the current message.
        let current_width = current.len() as i32 * FONT_WIDTH;
        // The next message is drawn immediately after the current one.
        let next_x_offset = x_offset + current_width;
        let _ = Text::with_baseline(next, Point::new(next_x_offset, FONT_VERT_OFFSET), style_next, Baseline::Top)
            .draw(target);
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}
