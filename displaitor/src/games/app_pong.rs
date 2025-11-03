use core::fmt::Write;
use core::marker::PhantomData;

use embedded_graphics::geometry::Point;
use embedded_graphics::mono_font::{ascii::FONT_6X9, MonoTextStyle};
use embedded_graphics::prelude::*;
use embedded_graphics::primitives::{PrimitiveStyle, Rectangle};
use embedded_graphics::text::Text;

use crate::string_buffer::FixedBuffer;
use crate::trait_app::{Color, RenderStatus, UpdateResult};
use crate::{string_buffer, App, AudioID, Controls, KeyReleaseEvent};

// TODO: Make screen size a parameter of the App struct.
#[derive(Clone, PartialEq, Debug)]
pub struct Pong<D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    ball_pos: Point,
    ball_velocity: Point,
    paddle1_pos: i32,
    paddle2_pos: i32,
    paddle_height: i32,
    paddle_width: i32,
    ball_size: i32,
    screen_width: i32,
    screen_height: i32,
    score1: i32,
    score2: i32,

    last_update: i64,
    dead: bool,
    close_request: KeyReleaseEvent,

    _marker: PhantomData<D>,
}

impl<D, C> Pong<D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub fn new(screen_width: u32, screen_height: u32) -> Self {
        Self {
            ball_pos: Point::new(screen_width as i32 / 2, screen_height as i32 / 2),
            ball_velocity: Point::new(1, 1),
            paddle1_pos: screen_height as i32 / 2 - 20,
            paddle2_pos: screen_height as i32 / 2 - 20,
            paddle_height: 10,
            paddle_width: 3,
            ball_size: 3,
            screen_width: screen_width as i32,
            screen_height: screen_height as i32,
            score1: 0,
            score2: 0,

            last_update: 0,
            dead: false,
            close_request: KeyReleaseEvent::new(),

            _marker: Default::default(),
        }
    }
}

impl<D, C> App for Pong<D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        self.dead = false;
        self.last_update = 0;
        self.close_request.reset();
    }

    fn update(&mut self, dt_us: i64, t_us: i64, controls: &Controls) -> UpdateResult {
        // Kill game with 'B'
        self.close_request.update(controls.buttons_b);

        // Time gate
        const MIN_UPDATE_DT_US: i64 = 20 * 1000; // 20 ms
        if t_us - self.last_update < MIN_UPDATE_DT_US {
            return RenderStatus::NoVisibleChange.into();
        }
        self.last_update = t_us;

        // Update paddles based on controls
        const MOVEMENT_SPEED: i32 = 2;
        if controls.dpad_down {
            self.paddle1_pos = (self.paddle1_pos - MOVEMENT_SPEED).max(0);
        }
        if controls.dpad_up {
            self.paddle1_pos =
                (self.paddle1_pos + MOVEMENT_SPEED).min(self.screen_height - self.paddle_height);
        }

        // Update ball position
        self.ball_pos.x += self.ball_velocity.x;
        self.ball_pos.y += self.ball_velocity.y;

        let mut audio_id = None;

        // Bounce ball off the top and bottom walls
        if self.ball_pos.y <= 0 || self.ball_pos.y >= self.screen_height - self.ball_size {
            self.ball_velocity.y = -self.ball_velocity.y;
            // TODO: audio_id = AudioID::Dumpf;
        }

        // Check for paddle collisions
        if self.ball_pos.x <= self.paddle_width {
            if self.ball_pos.y >= self.paddle1_pos
                && self.ball_pos.y <= self.paddle1_pos + self.paddle_height
            {
                self.ball_velocity.x = -self.ball_velocity.x;
                audio_id = Some(AudioID::Ping);
            } else {
                self.score2 += 1;
                self.ball_pos = Point::new(self.screen_width / 2, self.screen_height / 2);
            }
        }

        if self.ball_pos.x >= self.screen_width - self.paddle_width - self.ball_size {
            if self.ball_pos.y >= self.paddle2_pos
                && self.ball_pos.y <= self.paddle2_pos + self.paddle_height
            {
                self.ball_velocity.x = -self.ball_velocity.x;
                audio_id = Some(AudioID::Pong);
            } else {
                self.score1 += 1;
                self.ball_pos = Point::new(self.screen_width / 2, self.screen_height / 2);
            }
        }

        // Paddle 2 'AI'
        if self.ball_pos.y > self.paddle2_pos + self.paddle_height / 2 {
            self.paddle2_pos = (self.paddle2_pos + 2).min(self.screen_height - self.paddle_height);
        } else if self.ball_pos.y < self.paddle2_pos + self.paddle_height / 2 {
            self.paddle2_pos = (self.paddle2_pos - 2).max(0);
        }

        UpdateResult {
            render_result: RenderStatus::VisibleChange,
            audio_queue_request: audio_id,
        }
    }

    fn render(&self, target: &mut Self::Target) {
        // Clear the screen
        let _background = Rectangle::new(
            Point::zero(),
            Size::new(self.screen_width as u32, self.screen_height as u32),
        )
        .into_styled(PrimitiveStyle::with_fill(Self::Color::BLACK))
        .draw(target);

        // Cache colors - avoid repeated Color trait lookups
        let color1 = Self::Color::CYAN;
        let color2 = Self::Color::MAGENTA;
        let color_white = Self::Color::WHITE;
        
        // Draw paddles
        let _paddle1 = Rectangle::new(
            Point::new(0, self.paddle1_pos),
            Size::new(self.paddle_width as u32, self.paddle_height as u32),
        )
        .into_styled(PrimitiveStyle::with_fill(color1))
        .draw(target);

        let _paddle2 = Rectangle::new(
            Point::new(self.screen_width - self.paddle_width, self.paddle2_pos),
            Size::new(self.paddle_width as u32, self.paddle_height as u32),
        )
        .into_styled(PrimitiveStyle::with_fill(color2))
        .draw(target);

        // Display scores - reuse buffer and cache styles
        let mut text_buffer = FixedBuffer::<32>::new();
        const SCORE_PREFIX_P1: &str = "P1: ";
        const SCORE_PREFIX_P2: &str = "P2: ";

        // - Score 1
        text_buffer.clear();
        let _ = write!(&mut text_buffer, "{}{}", SCORE_PREFIX_P1, self.score1);
        let score_style1 = MonoTextStyle::new(&FONT_6X9, color1);
        let _score = Text::new(text_buffer.as_str(), Point::new(10, 10), score_style1).draw(target);

        // - Score 2
        text_buffer.clear();
        let _ = write!(&mut text_buffer, "{}{}", SCORE_PREFIX_P2, self.score2);
        let score_style2 = MonoTextStyle::new(&FONT_6X9, color2);
        let _score = Text::new(text_buffer.as_str(), Point::new(10, 20), score_style2).draw(target);

        // Draw the ball
        let _ball = Rectangle::new(
            self.ball_pos,
            Size::new(self.ball_size as u32, self.ball_size as u32),
        )
        .into_styled(PrimitiveStyle::with_fill(color_white))
        .draw(target);
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}
