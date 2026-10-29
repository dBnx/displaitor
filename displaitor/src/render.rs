use embedded_graphics::{
    image::Image,
    mono_font::{
        MonoTextStyle,
        ascii::{FONT_4X6, FONT_6X10},
        iso_8859_10::FONT_10X20,
    },
    pixelcolor::{Rgb565, Rgb888},
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
    text::{Baseline, Text},
};
use tinyqoi::Qoi;

use crate::{
    AppId, Engine, HEIGHT, Screen, WIDTH, content, cozy,
    games::{Cell, Pong},
    menu_view::{self, EntryKind, MenuRow, MenuView},
    navigation::Action,
};

impl<const N: usize> Engine<N> {
    /// Draw one complete frame. Errors are propagated to the owning adapter.
    /// Content is clipped to the physical 64×32 display, including scrolling text.
    pub fn render<D: DrawTarget<Color = Rgb565>>(&self, target: &mut D) -> Result<(), D::Error> {
        let mut target = target.clipped(&Rectangle::new(Point::zero(), Size::new(WIDTH, HEIGHT)));
        if matches!(self.screen, Screen::Menu(_)) {
            let navigation = &self.navigation;
            let mut rows = [MenuRow {
                label: "",
                kind: EntryKind::Action,
                selected: false,
            }; 3];
            let start = navigation.visible_start();
            let count = navigation.visible_len();
            for (row, output) in rows.iter_mut().take(count).enumerate() {
                let entry = navigation
                    .visible_entry(row)
                    .expect("row is within validated viewport");
                *output = MenuRow {
                    label: entry.label,
                    kind: match entry.action {
                        Action::Menu(_) => EntryKind::Folder,
                        Action::App(_) => EntryKind::Action,
                    },
                    selected: start + row == navigation.selected_index(),
                };
            }
            return menu_view::render(
                MenuView {
                    title: navigation.current_menu().title,
                    rows: &rows[..count],
                    position: navigation.selected_index(),
                    total: navigation.current_menu().entries.len(),
                },
                &mut target,
            );
        }
        if self.screen == Screen::App(AppId::Canvas) {
            return self.canvas.render(&mut target);
        }
        // Cozy clips are opaque and cover the whole panel. Decode once into the
        // existing back buffer, without first writing 2048 redundant black pixels.
        if !matches!(
            self.screen,
            Screen::App(
                AppId::CozyFarm
                    | AppId::CozyWinter
                    | AppId::CozyOkami
                    | AppId::CozyWitcher
                    | AppId::CozyReef
                    | AppId::Fire
                    | AppId::CozyPalico
                    | AppId::CozyRathalos
                    | AppId::CozyZinogre
                    | AppId::CozyPoogie
            )
        ) {
            target.clear(Rgb565::BLACK)?;
        }
        match self.screen {
            Screen::Splash
            | Screen::App(
                AppId::Nyan
                | AppId::Hyper
                | AppId::CozyFarm
                | AppId::CozyWinter
                | AppId::CozyOkami
                | AppId::CozyWitcher
                | AppId::CozyReef
                | AppId::Fire
                | AppId::CozyPalico
                | AppId::CozyRathalos
                | AppId::CozyZinogre
                | AppId::CozyPoogie,
            ) => {
                let bytes = match self.screen {
                    Screen::App(
                        id @ (AppId::CozyFarm
                        | AppId::CozyWinter
                        | AppId::CozyOkami
                        | AppId::CozyWitcher
                        | AppId::CozyReef
                        | AppId::Fire
                        | AppId::CozyPalico
                        | AppId::CozyRathalos
                        | AppId::CozyZinogre
                        | AppId::CozyPoogie),
                    ) => cozy::clip(id).frame(self.frame),
                    Screen::App(id) => content::frames(Some(id))[self.frame],
                    _ => content::frames(None)[self.frame],
                };
                // Assets are validated in host tests. A malformed replacement must
                // not panic firmware; display an actionable fallback instead.
                if let Ok(image) = Qoi::new(bytes) {
                    let mut rgb888 = target.color_converted::<Rgb888>();
                    let positioned = if matches!(
                        self.screen,
                        Screen::App(
                            AppId::CozyFarm
                                | AppId::CozyWinter
                                | AppId::CozyOkami
                                | AppId::CozyWitcher
                                | AppId::CozyReef
                                | AppId::Fire
                                | AppId::CozyPalico
                                | AppId::CozyRathalos
                                | AppId::CozyZinogre
                                | AppId::CozyPoogie
                        )
                    ) {
                        Image::new(&image, Point::zero())
                    } else {
                        Image::with_center(&image, Point::new(32, 16))
                    };
                    positioned.draw(&mut rgb888)?;
                    if let (Screen::App(id), Some(us)) = (self.screen, self.cozy_action_us) {
                        cozy::action(id)
                            .draw((us / cozy::ACTION_PERIOD_US) as usize, &mut target)?;
                    }
                } else {
                    target.clear(Rgb565::BLACK)?;
                    text("Bad asset", Point::new(0, 10), Rgb565::RED, &mut target)?;
                }
            }
            Screen::Menu(_) => {}
            Screen::App(AppId::Canvas) => unreachable!("rendered above"),
            Screen::App(AppId::Names) => {
                let current = content::NAMES[self.name_index];
                let next = content::NAMES[self.name_next];
                let x = -self.name_offset;
                Text::with_baseline(
                    current.text,
                    Point::new(x, 6),
                    MonoTextStyle::new(&FONT_10X20, self.name_color),
                    Baseline::Top,
                )
                .draw(&mut target)?;
                let width = current.width;
                Text::with_baseline(
                    next.text,
                    Point::new(x + width, 6),
                    MonoTextStyle::new(&FONT_10X20, self.next_color),
                    Baseline::Top,
                )
                .draw(&mut target)?;
            }
            Screen::App(AppId::Pong) => {
                if let Some(pong) = self.pong() {
                    rectangle(
                        Cell { x: 0, y: pong.left },
                        Pong::PADDLE_WIDTH,
                        Pong::PADDLE_HEIGHT,
                        Rgb565::CYAN,
                        &mut target,
                    )?;
                    rectangle(
                        Cell {
                            x: WIDTH as u8 - Pong::PADDLE_WIDTH,
                            y: pong.right,
                        },
                        Pong::PADDLE_WIDTH,
                        Pong::PADDLE_HEIGHT,
                        Rgb565::MAGENTA,
                        &mut target,
                    )?;
                    number(pong.scores[0], Point::new(12, 0), Rgb565::CYAN, &mut target)?;
                    number(
                        pong.scores[1],
                        Point::new(36, 0),
                        Rgb565::MAGENTA,
                        &mut target,
                    )?;
                    rectangle(
                        pong.ball,
                        Pong::BALL_SIZE,
                        Pong::BALL_SIZE,
                        Rgb565::WHITE,
                        &mut target,
                    )?;
                }
            }
            Screen::App(AppId::Snake) => {
                if let Some(snake) = self.snake() {
                    for (index, &cell) in snake.body[..snake.len].iter().enumerate() {
                        rectangle(
                            cell,
                            1,
                            1,
                            if index == 0 {
                                Rgb565::WHITE
                            } else {
                                Rgb565::GREEN
                            },
                            &mut target,
                        )?;
                    }
                    if let Some(cell) = snake.food {
                        rectangle(cell, 1, 1, Rgb565::RED, &mut target)?;
                    }
                    if snake.over {
                        text(
                            if snake.food.is_none() {
                                "You win!"
                            } else {
                                "Game over"
                            },
                            Point::new(3, 1),
                            Rgb565::CYAN,
                            &mut target,
                        )?;
                        text("A: retry", Point::new(6, 21), Rgb565::WHITE, &mut target)?;
                    }
                }
            }
        }
        Ok(())
    }
}

fn text<D: DrawTarget<Color = Rgb565>>(
    value: &str,
    point: Point,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    Text::with_baseline(
        value,
        point,
        MonoTextStyle::new(&FONT_6X10, color),
        Baseline::Top,
    )
    .draw(target)?;
    Ok(())
}

fn rectangle<D: DrawTarget<Color = Rgb565>>(
    cell: Cell,
    width: u8,
    height: u8,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    Rectangle::new(
        Point::new(i32::from(cell.x), i32::from(cell.y)),
        Size::new(u32::from(width), u32::from(height)),
    )
    .into_styled(PrimitiveStyle::with_fill(color))
    .draw(target)
}

fn number<D: DrawTarget<Color = Rgb565>>(
    mut value: u16,
    point: Point,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    let mut digits = [b'0'; 5];
    let mut start = digits.len() - 1;
    loop {
        digits[start] = b'0' + (value % 10) as u8;
        value /= 10;
        if value == 0 || start == 0 {
            break;
        }
        start -= 1;
    }
    // Each byte was generated from an ASCII decimal digit.
    let value = core::str::from_utf8(&digits[start..]).unwrap_or("?");
    Text::with_baseline(
        value,
        point,
        MonoTextStyle::new(&FONT_4X6, color),
        Baseline::Top,
    )
    .draw(target)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_embedded_image_decodes_the_expected_pixels() {
        for app in [None, Some(AppId::Nyan), Some(AppId::Hyper)] {
            for bytes in content::frames(app) {
                let image = Qoi::new(bytes).expect("Embedded QOI asset");
                // The original first logo is one pixel wider than the panel.
                let expected_width = if app.is_none() && bytes == &content::SPLASH[0] {
                    65
                } else {
                    WIDTH
                };
                assert_eq!(image.size(), Size::new(expected_width, HEIGHT));
                let expected_pixels = (expected_width * HEIGHT) as usize;
                assert_eq!(
                    image.pixels().take(expected_pixels).count(),
                    expected_pixels
                );
            }
        }
    }
}
