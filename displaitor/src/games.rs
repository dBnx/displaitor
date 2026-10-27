use crate::{AudioId, Controls, HEIGHT, WIDTH};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Cell {
    pub x: u8,
    pub y: u8,
}

pub(crate) struct Pong {
    pub ball: Cell,
    pub left: u8,
    pub right: u8,
    pub scores: [u16; 2],
    dx: i8,
    dy: i8,
    ai_step: bool,
}

impl Pong {
    pub const PADDLE_HEIGHT: u8 = 10;
    pub const PADDLE_WIDTH: u8 = 3;
    pub const BALL_SIZE: u8 = 3;

    pub fn new() -> Self {
        Self {
            ball: Cell { x: 32, y: 16 },
            left: 11,
            right: 11,
            scores: [0; 2],
            dx: 1,
            dy: 1,
            ai_step: false,
        }
    }

    pub fn step(&mut self, controls: Controls) -> Option<AudioId> {
        let movement = i16::from(controls.dpad_down) - i16::from(controls.dpad_up);
        self.left = (i16::from(self.left) + 2 * movement)
            .clamp(0, HEIGHT as i16 - i16::from(Self::PADDLE_HEIGHT)) as u8;
        // Half the ball's vertical speed gives the player a reachable score.
        self.ai_step = !self.ai_step;
        if self.ai_step {
            let target = i16::from(self.ball.y) - i16::from(Self::PADDLE_HEIGHT / 2);
            self.right = (i16::from(self.right) + (target - i16::from(self.right)).clamp(-1, 1))
                .clamp(0, HEIGHT as i16 - i16::from(Self::PADDLE_HEIGHT))
                as u8;
        }
        let x = i16::from(self.ball.x) + i16::from(self.dx);
        let y = i16::from(self.ball.y) + i16::from(self.dy);
        let bottom = HEIGHT as i16 - i16::from(Self::BALL_SIZE);
        if y <= 0 || y >= bottom {
            self.dy = -self.dy;
        }
        self.ball.y = y.clamp(0, bottom) as u8;
        self.ball.x = x.clamp(0, WIDTH as i16 - i16::from(Self::BALL_SIZE)) as u8;
        let paddle = if self.dx < 0 && x <= i16::from(Self::PADDLE_WIDTH) {
            Some((self.left, 1, AudioId::Ping))
        } else if self.dx > 0 && x >= WIDTH as i16 - i16::from(Self::PADDLE_WIDTH + Self::BALL_SIZE)
        {
            Some((self.right, 0, AudioId::Pong))
        } else {
            None
        };
        if let Some((top, scorer, audio)) = paddle {
            // Intersect the entire ball, including grazes against paddle edges.
            if self.ball.y < top + Self::PADDLE_HEIGHT && self.ball.y + Self::BALL_SIZE > top {
                self.dx = -self.dx;
                return Some(audio);
            }
            self.scores[scorer] = self.scores[scorer].saturating_add(1);
            self.ball = Cell { x: 32, y: 16 };
            self.dx = -self.dx;
        }
        None
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Direction {
    Up,
    Down,
    Left,
    Right,
}

/// Fixed storage bounds both execution time and RAM use. Filling the body wins.
pub(crate) struct Snake {
    pub body: [Cell; Self::CAPACITY],
    pub len: usize,
    pub food: Option<Cell>,
    pub over: bool,
    direction: Direction,
    pending: Direction,
    random: u32,
}

impl Snake {
    pub const CAPACITY: usize = 128;

    pub fn new() -> Self {
        let mut snake = Self {
            body: [Cell::default(); Self::CAPACITY],
            len: 3,
            food: None,
            over: false,
            direction: Direction::Right,
            pending: Direction::Right,
            random: 0xdead_beef,
        };
        snake.body[..3].copy_from_slice(&[
            Cell { x: 32, y: 16 },
            Cell { x: 31, y: 16 },
            Cell { x: 30, y: 16 },
        ]);
        snake.spawn_food();
        snake
    }

    pub fn steer(&mut self, controls: Controls) {
        // At most one pending direction per movement step. Each request is checked
        // against the actual direction, so two rapid turns cannot reverse into the neck.
        self.pending = match self.direction {
            Direction::Up | Direction::Down if controls.dpad_left != controls.dpad_right => {
                if controls.dpad_left {
                    Direction::Left
                } else {
                    Direction::Right
                }
            }
            Direction::Left | Direction::Right if controls.dpad_up != controls.dpad_down => {
                if controls.dpad_up {
                    Direction::Up
                } else {
                    Direction::Down
                }
            }
            _ => self.pending,
        };
    }

    pub fn step(&mut self) -> Option<AudioId> {
        if self.over {
            return None;
        }
        self.direction = self.pending;
        let head = self.body[0];
        let (dx, dy) = match self.direction {
            Direction::Up => (0, -1),
            Direction::Down => (0, 1),
            Direction::Left => (-1, 0),
            Direction::Right => (1, 0),
        };
        let x = i16::from(head.x) + dx;
        let y = i16::from(head.y) + dy;
        if !(0..WIDTH as i16).contains(&x) || !(0..HEIGHT as i16).contains(&y) {
            self.over = true;
            return Some(AudioId::GameOver);
        }
        let next = Cell {
            x: x as u8,
            y: y as u8,
        };
        let grows = self.food == Some(next);
        // The tail vacates its cell on a non-growing move.
        let occupied = if grows { self.len } else { self.len - 1 };
        if self.body[..occupied].contains(&next) {
            self.over = true;
            return Some(AudioId::GameOver);
        }
        if grows && self.len < Self::CAPACITY {
            self.len += 1;
        }
        self.body.copy_within(..self.len - 1, 1);
        self.body[0] = next;
        if grows {
            if self.len == Self::CAPACITY {
                self.over = true;
                self.food = None;
            } else {
                self.spawn_food();
            }
            return Some(AudioId::Nom);
        }
        None
    }

    fn spawn_food(&mut self) {
        self.random ^= self.random << 13;
        self.random ^= self.random >> 17;
        self.random ^= self.random << 5;
        let start = self.random as usize % (WIDTH * HEIGHT) as usize;
        // A deterministic bounded scan guarantees food never overlaps the snake.
        for offset in 0..(WIDTH * HEIGHT) as usize {
            let index = (start + offset) % (WIDTH * HEIGHT) as usize;
            let cell = Cell {
                x: (index % WIDTH as usize) as u8,
                y: (index / WIDTH as usize) as u8,
            };
            if !self.body[..self.len].contains(&cell) {
                self.food = Some(cell);
                return;
            }
        }
        self.food = None;
        self.over = true;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pong_remains_inside_display_and_paddles_follow_direction() {
        let mut pong = Pong::new();
        pong.step(Controls {
            dpad_up: true,
            ..Controls::default()
        });
        assert_eq!(pong.left, 9);
        for i in 0..100_000 {
            pong.step(Controls {
                dpad_down: i % 90 < 45,
                dpad_up: i % 90 >= 45,
                ..Controls::default()
            });
            assert!(pong.left <= 22 && pong.right <= 22);
            assert!(pong.ball.x <= 61 && pong.ball.y <= 29);
        }
    }

    #[test]
    fn snake_handles_full_capacity_without_inserting_past_buffer() {
        let mut snake = Snake::new();
        snake.len = Snake::CAPACITY - 1;
        for (index, cell) in snake.body[..snake.len].iter_mut().enumerate() {
            *cell = Cell {
                x: (index % 64) as u8,
                y: (index / 64) as u8,
            };
        }
        snake.body[0] = Cell { x: 32, y: 16 };
        snake.food = Some(Cell { x: 33, y: 16 });
        assert_eq!(snake.step(), Some(AudioId::Nom));
        assert_eq!(snake.len, Snake::CAPACITY);
        assert!(snake.over);
        assert_eq!(snake.food, None);
    }

    #[test]
    fn pong_player_can_score_and_opponent_still_returns_rallies() {
        let mut pong = Pong::new();
        let mut returns = 0;
        for _ in 0..10_000 {
            let target = pong.ball.y.saturating_sub(Pong::PADDLE_HEIGHT / 2);
            returns += usize::from(
                pong.step(Controls {
                    dpad_up: pong.left > target,
                    dpad_down: pong.left < target,
                    ..Controls::default()
                }) == Some(AudioId::Pong),
            );
        }
        assert!(pong.scores[0] > 0, "opponent must be beatable");
        assert!(returns > 0, "opponent must still return some shots");
        let mut undefended = Pong::new();
        for _ in 0..10_000 {
            let _ = undefended.step(Controls::default());
        }
        assert!(undefended.scores[1] > 0, "player must still defend");
    }

    #[test]
    fn snake_can_enter_vacating_tail_but_not_an_occupied_growing_tail() {
        let mut snake = Snake::new();
        snake.len = 4;
        snake.body[..4].copy_from_slice(&[
            Cell { x: 2, y: 2 },
            Cell { x: 2, y: 3 },
            Cell { x: 3, y: 3 },
            Cell { x: 3, y: 2 },
        ]);
        snake.food = Some(Cell { x: 10, y: 10 });
        assert_eq!(snake.step(), None);
        assert_eq!(snake.body[0], Cell { x: 3, y: 2 });
        assert!(!snake.over);

        let mut growing = Snake::new();
        growing.len = 4;
        growing.body[..4].copy_from_slice(&[
            Cell { x: 2, y: 2 },
            Cell { x: 2, y: 3 },
            Cell { x: 3, y: 3 },
            Cell { x: 3, y: 2 },
        ]);
        growing.food = Some(Cell { x: 3, y: 2 });
        assert_eq!(growing.step(), Some(AudioId::GameOver));
        assert!(growing.over);
    }

    #[test]
    fn snake_eats_grows_and_reports_wall_collision_only_once() {
        let mut snake = Snake::new();
        snake.food = Some(Cell { x: 33, y: 16 });
        assert_eq!(snake.step(), Some(AudioId::Nom));
        assert_eq!(snake.len, 4);
        assert!(!snake.body[..snake.len].contains(&snake.food.unwrap()));
        for _ in 0..30 {
            assert!(!snake.over);
            let _ = snake.step();
        }
        assert_eq!(snake.step(), Some(AudioId::GameOver));
        assert!(snake.over);
        assert_eq!(snake.step(), None);
    }

    #[test]
    fn snake_food_is_in_bounds_and_unoccupied() {
        let mut snake = Snake::new();
        for _ in 0..1000 {
            snake.spawn_food();
            let food = snake.food.unwrap();
            assert!(u32::from(food.x) < WIDTH && u32::from(food.y) < HEIGHT);
            assert!(!snake.body[..snake.len].contains(&food));
        }
    }

    #[test]
    fn snake_can_win_a_complete_game_without_overlapping_or_exceeding_capacity() {
        let mut snake = Snake::new();
        // A cycle through every board cell, excluding column zero until the return.
        for _ in 0..Snake::CAPACITY * (WIDTH * HEIGHT) as usize {
            if snake.over {
                break;
            }
            let Cell { x, y } = snake.body[0];
            let controls = if x == 0 && y != 0 {
                Controls {
                    dpad_up: true,
                    ..Controls::default()
                }
            } else if y % 2 == 0 && x < WIDTH as u8 - 1 {
                Controls {
                    dpad_right: true,
                    ..Controls::default()
                }
            } else if y % 2 != 0 && x > 1 || y == HEIGHT as u8 - 1 {
                Controls {
                    dpad_left: true,
                    ..Controls::default()
                }
            } else {
                Controls {
                    dpad_down: true,
                    ..Controls::default()
                }
            };
            snake.steer(controls);
            let _ = snake.step();
            assert!(snake.len <= Snake::CAPACITY);
            assert!(!snake.body[1..snake.len].contains(&snake.body[0]));
        }
        assert!(snake.over);
        assert_eq!(snake.len, Snake::CAPACITY);
        assert_eq!(snake.food, None);
    }

    #[test]
    fn snake_turns_follow_screen_directions() {
        // Start vertically before testing left/right, since direct reversals are forbidden.
        for (vertical, dy) in [(Direction::Up, -1_i16), (Direction::Down, 1)] {
            for (horizontal, dx) in [(Direction::Left, -1_i16), (Direction::Right, 1)] {
                let mut snake = Snake::new();
                snake.food = Some(Cell { x: 0, y: 0 });
                snake.steer(Controls {
                    dpad_up: vertical == Direction::Up,
                    dpad_down: vertical == Direction::Down,
                    ..Controls::default()
                });
                assert_eq!(snake.step(), None);
                assert_eq!(
                    snake.body[0],
                    Cell {
                        x: 32,
                        y: (16 + dy) as u8
                    }
                );
                snake.steer(Controls {
                    dpad_left: horizontal == Direction::Left,
                    dpad_right: horizontal == Direction::Right,
                    ..Controls::default()
                });
                assert_eq!(snake.step(), None);
                assert_eq!(
                    snake.body[0],
                    Cell {
                        x: (32 + dx) as u8,
                        y: (16 + dy) as u8
                    }
                );
                assert!(!snake.over);
            }
        }
    }

    #[test]
    fn snake_rapid_turns_cannot_reverse_into_neck() {
        let mut snake = Snake::new();
        snake.steer(Controls {
            dpad_up: true,
            ..Controls::default()
        });
        snake.steer(Controls {
            dpad_left: true,
            ..Controls::default()
        });
        snake.step();
        assert_eq!(snake.body[0], Cell { x: 32, y: 15 });
        assert!(!snake.over);
    }
}
