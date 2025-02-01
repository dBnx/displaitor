use core::marker::PhantomData;

use embedded_graphics::{
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
};
use heapless::Vec;

use crate::{App, Controls};

pub struct Snake<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C> 
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,  
{
    body: Vec<Point, MAX_LEN>,
    dir: Direction,
    food: Option<Point>,
    grow: bool,
    time: i32,
    _marker: PhantomData<D>,
}

#[derive(PartialEq)]
pub enum Direction {
    Up,
    Down,
    Left,
    Right,
}

impl<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C> Snake<SCR_W, SCR_H, MAX_LEN, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor,  
{
    pub fn new() -> Self {
        let mut body = Vec::new();
        body.push(Point::new(SCR_W as i32 / 2, SCR_H as i32 / 2))
            .unwrap(); // Start with one segment

        Self {
            body,
            dir: Direction::Right,
            food: Some(Point::new(5, 5)), // Example initial food position
            grow: false,
            time: 0,
            _marker: Default::default(),
        }
    }

    fn spawn_food(&mut self) {
        // Spawn food at a fixed location for simplicity
        // Replace this with random placement if needed
        self.food = Some(Point::new(
            (SCR_H / 3) as i32,
            (SCR_W / 3) as i32,
        ));
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
            self.food = None; // Remove food, new food will spawn in update
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
        head.x < 0
            || head.y < 0
            || head.x >= SCR_W as i32
            || head.y >= SCR_H as i32
    }
}

impl<const SCR_W: u32, const SCR_H: u32, const MAX_LEN: usize, D, C> App for Snake<SCR_W, SCR_H, MAX_LEN, D, C>
where
    D: DrawTarget<Color = C>,
    C: PixelColor + RgbColor, 
{
    type Target = D;
    type Color = C;

    fn update(&mut self, dt: i64, _t: i64, controls: &Controls) {
        self.time += dt as i32;
        const TIME_BETWEEN_UPDATE: i32 = 90;
        if self.time < TIME_BETWEEN_UPDATE {
            return;
        }
        self.time -= TIME_BETWEEN_UPDATE;

        // Handle input for direction
        if controls.dpad_up && self.dir != Direction::Down {
            self.dir = Direction::Up;
        } else if controls.dpad_down && self.dir != Direction::Up {
            self.dir = Direction::Down;
        } else if controls.dpad_left && self.dir != Direction::Right {
            self.dir = Direction::Left;
        } else if controls.dpad_right && self.dir != Direction::Left {
            self.dir = Direction::Right;
        }

        // Move the snake
        self.move_snake();

        // Check for collisions
        if self.check_collision() || self.check_bounds() {
            todo!("");
            // println!("Game over!");
        }

        // Spawn new food if needed
        if self.food.is_none() {
            self.spawn_food();
        }
    }

    fn render(&mut self, target: &mut Self::Target)
    {
        // Draw the snake
        let snake_style_head = PrimitiveStyle::with_fill(C::WHITE);
        let snake_style_pri = PrimitiveStyle::with_fill(C::GREEN);
        let snake_style_sec = PrimitiveStyle::with_fill(C::YELLOW);
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

    fn teardown(&mut self) {
        // TODO
    }

    fn close_request(&self) -> bool {
        todo!()
    }
}
