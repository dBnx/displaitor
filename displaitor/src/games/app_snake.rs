use core::{fmt::Write, marker::PhantomData};

use embedded_graphics::{
    mono_font::{ascii::FONT_6X9, MonoTextStyle},
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
    text::Text,
};
use heapless::Vec;
use tinyrand::{Rand, Seeded, StdRand};

use crate::{
    string_buffer::{self, FixedBuffer},
    trait_app::Color,
    App, Controls, KeyReleaseEvent,
};

pub struct Snake<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    body: Vec<Point, MAX_LEN>,
    dir: Direction,
    food: Option<Point>,
    grow: bool,

    prng: StdRand,

    dead: bool,
    close_request: KeyReleaseEvent,
    time: i32,
    last_update: i64,

    _marker: PhantomData<D>,
}

#[derive(PartialEq)]
pub enum Direction {
    Up,
    Down,
    Left,
    Right,
}

impl<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C>
    Snake<SCR_W, SCR_H, MAX_LEN, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,
{
    pub fn new() -> Self {
        let mut prng = StdRand::seed(0xDEAD_BEEF);
        let mut body = Vec::new();
        body.push(Point::new(SCR_W as i32 / 2, SCR_H as i32 / 2))
            .unwrap(); // Start with one segment

        Self {
            body,
            dir: Direction::Right,
            food: Some(random_position::<SCR_W, SCR_H>(&mut prng)),
            grow: false,

            time: 0,
            prng,
            dead: false,
            close_request: KeyReleaseEvent::new(),
            last_update: 0,

            _marker: Default::default(),
        }
    }

    fn spawn_food(&mut self) {
        self.food = Some(random_position::<SCR_W, SCR_H>(&mut self.prng));
    }

    fn move_snake(&mut self) {
        let head = self.body[0];
        let new_head = match self.dir {
            Direction::Up => head + Point::new(0, -1),
            Direction::Down => head + Point::new(0, 1),
            Direction::Left => head + Point::new(-1, 0),
            Direction::Right => head + Point::new(1, 0),
        };

        // Insert the new head at the front of the body
        self.body.insert(0, new_head).unwrap();

        // Check if the snake ate food
        if Some(new_head) == self.food {
            self.grow = true;
            self.food = None;
        }

        // Remove the tail unless the snake is growing
        if !self.grow {
            self.body.pop();
        } else {
            self.grow = false;
        }
    }

    fn check_collision(&self) -> bool {
        let head = self.body[0];
        // Check for self-collision
        self.body.iter().skip(1).any(|&segment| segment == head)
    }

    fn check_bounds(&self) -> bool {
        let head = self.body[0];
        head.x < 0 || head.y < 0 || head.x >= SCR_W as i32 || head.y >= SCR_H as i32
    }
}

impl<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C> App
    for Snake<SCR_W, SCR_H, MAX_LEN, D, C>
where
    D: DrawTarget<Color = C>,
    C: Color,
{
    type Target = D;
    type Color = C;

    fn reset_state(&mut self) {
        let mut body = Vec::new();
        body.push(Point::new(SCR_W as i32 / 2, SCR_H as i32 / 2))
            .unwrap(); // Start with one segment

        self.body = body;
        self.food = Some(random_position::<SCR_W, SCR_H>(&mut self.prng));
        self.dir = Direction::Right;
        self.grow = false;

        self.dead = false;
        self.close_request.reset();
        self.last_update = 0;
    }

    fn update(&mut self, dt: i64, t: i64, controls: &Controls) -> bool {
        // Kill game with 'B'
        self.close_request.update(controls.buttons_b);

        if controls.dpad_up && self.dir != Direction::Down {
            self.dir = Direction::Up;
        } else if controls.dpad_down && self.dir != Direction::Up {
            self.dir = Direction::Down;
        } else if controls.dpad_left && self.dir != Direction::Right {
            self.dir = Direction::Left;
        } else if controls.dpad_right && self.dir != Direction::Left {
            self.dir = Direction::Right;
        }

        // Time gate
        const MIN_UPDATE_DT_US: i64 = 60 * 1000; // 100 ms
        if t - self.last_update < MIN_UPDATE_DT_US {
            return false;
        }
        self.last_update = t;

        // Move the snake
        self.move_snake();

        // Check for collisions
        if self.check_collision() || self.check_bounds() {
            self.dead = true;
        }

        // Spawn new food if needed
        if self.food.is_none() {
            self.spawn_food();
        }

        true
    }

    fn render(&self, target: &mut Self::Target) {
        // Draw some stats
        let mut text_buffer = FixedBuffer::<32>::new();
        let gray = C::BLUE; // 0x404040.try_into().unwrap();
        let score_style = MonoTextStyle::new(&FONT_6X9, gray);

        text_buffer.clear();
        let _ = write!(&mut text_buffer, "Len: {}", self.body.len());
        let _score = Text::new(text_buffer.as_str(), Point::new(10, 10), score_style).draw(target);

        // Draw the snake
        let snake_style_head = PrimitiveStyle::with_fill(C::CSS_GRAY);
        let snake_style_pri = PrimitiveStyle::with_fill(C::CSS_GREEN_YELLOW);
        let snake_style_sec = PrimitiveStyle::with_fill(C::GREEN);
        for (i, &segment) in self.body.iter().enumerate() {
            let style = match i {
                0 => snake_style_head,
                _ if i % 2 == 1 => snake_style_sec,
                _ => snake_style_pri,
            };
            let _segment = Rectangle::new(segment, Size::new(1, 1))
                .into_styled(style)
                .draw(target);
        }

        // Draw the food
        if let Some(food_pos) = self.food {
            let food_style = PrimitiveStyle::with_fill(C::RED);
            let _food = Rectangle::new(food_pos, Size::new(1, 1))
                .into_styled(food_style)
                .draw(target);
        }
    }

    fn teardown(&mut self) {}

    fn close_request(&self) -> bool {
        self.close_request.fired()
    }
}

fn random_position<const SCR_W: u32, const SCR_H: u32>(prng: &mut StdRand) -> Point {
    let x = prng.next_lim_u32(SCR_H) as i32;
    let y = prng.next_lim_u32(SCR_W) as i32;
    Point { x, y }
}
