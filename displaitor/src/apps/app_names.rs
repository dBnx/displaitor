#![allow(unused)]

use embedded_graphics::{
    mono_font::{ascii::FONT_4X6, ascii::FONT_6X9, MonoTextStyle},
    pixelcolor::Rgb565 as Rgb,
    prelude::*,
    primitives::{Circle, Line, PrimitiveStyle, Rectangle},
    text::Text,
};


static NAMES: &'static str = include_str!("../../assets/names.txt");

pub struct Names {}

fn render<D, E>(display: &mut D) -> Result<(), core::convert::Infallible>
where
    D: DrawTarget<Color = Rgb, Error = E>,
    E: core::error::Error + core::fmt::Debug, // C: PixelColor,
{
    let line_style = PrimitiveStyle::with_stroke(Rgb::WHITE, 1);
    let line_style_alt = PrimitiveStyle::with_stroke(Rgb::GREEN, 1);
    let text_style = MonoTextStyle::new(&FONT_4X6, Rgb::BLUE);

    Circle::new(Point::new(72 / 2, 8 / 2 + 3), 48 / 2)
        .into_styled(line_style)
        .draw(display)
        .unwrap();

    Line::new(
        Point::new(48 / 2, 16 / 2 + 3),
        Point::new(8 / 2, 16 / 2 + 3),
    )
    .into_styled(line_style)
    .draw(display)
    .unwrap();


    Line::new(
        Point::new(48 / 2, 16 / 2 + 3),
        Point::new(64 / 2, 32 / 2 + 3),
    )
    .into_styled(line_style)
    .draw(display)
    .unwrap();

    Rectangle::new(
        Point::new(79 / 2, 15 / 2 + 3),
        Size::new(34 / 2, 34 / 2 + 3),
    )
    .into_styled(line_style_alt)
    .draw(display)
    .unwrap();

    Text::new("Displaytor 1.0", Point::new(5, 5), text_style)
        .draw(display)
        .unwrap();

    Ok(())
}