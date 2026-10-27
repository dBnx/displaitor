//! Compact, allocation-free presentation for a hierarchical menu.
//!
//! Navigation owns menu traversal and supplies only the rows visible in this
//! frame. The renderer deliberately knows nothing about parent menus, so
//! adding deeper navigation does not add per-frame traversal work.

use embedded_graphics::{
    mono_font::{MonoTextStyle, ascii::FONT_4X6},
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
    text::{Baseline, Text},
};

const WIDTH: u32 = 64;
const HEIGHT: u32 = 32;
const HEADER_HEIGHT: u32 = 8;
const ROW_HEIGHT: i32 = 8;
const VISIBLE_ROWS: usize = 3;
const SCROLL_X: i32 = 63;
const SCROLL_TOP: i32 = HEADER_HEIGHT as i32 + 1;
const SCROLL_HEIGHT: i32 = HEIGHT as i32 - SCROLL_TOP;

const TITLE_TEXT: Rgb565 = Rgb565::BLACK;
const BACKGROUND: Rgb565 = Rgb565::BLACK;
const HEADER: Rgb565 = Rgb565::new(0, 24, 12);
const ACCENT: Rgb565 = Rgb565::new(10, 63, 31);
const MUTED: Rgb565 = Rgb565::new(7, 15, 14);
// Lowest neutral grey in RGB565: one red/blue step and two green half-steps.
const SCROLL_TRACK: Rgb565 = Rgb565::new(1, 2, 1);
const TEXT: Rgb565 = Rgb565::new(25, 53, 45);

/// The visual kind of a menu entry. Actions and folders have distinct marks.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EntryKind {
    Folder,
    Action,
}

/// One already-resolved row to draw. `selected` is independent of menu depth.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MenuRow<'a> {
    pub label: &'a str,
    pub kind: EntryKind,
    pub selected: bool,
}

/// A bounded view prepared by the navigation layer for one display frame.
///
/// `rows` should contain no more than three entries. `position` is the
/// zero-based absolute selected-entry index and `total` is the number of
/// entries in the current menu; these values drive a tiny edge scroll marker.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MenuView<'a> {
    pub title: &'a str,
    pub rows: &'a [MenuRow<'a>],
    pub position: usize,
    pub total: usize,
}

/// Draw a complete 64×32 menu frame without allocating or walking ancestors.
pub fn render<D: DrawTarget<Color = Rgb565>>(
    view: MenuView<'_>,
    target: &mut D,
) -> Result<(), D::Error> {
    target.clear(BACKGROUND)?;
    fill(
        Rectangle::new(Point::zero(), Size::new(WIDTH, HEADER_HEIGHT)),
        HEADER,
        target,
    )?;
    // Keep the separator dim so it cannot wash out the first menu row.
    fill(
        Rectangle::new(Point::new(0, HEADER_HEIGHT as i32 - 1), Size::new(WIDTH, 1)),
        MUTED,
        target,
    )?;

    draw_bounded(view.title, Point::new(3, 1), 14, TITLE_TEXT, target)?;

    for (index, row) in view.rows.iter().take(VISIBLE_ROWS).enumerate() {
        let y = HEADER_HEIGHT as i32 + index as i32 * ROW_HEIGHT;
        let row_text = if row.selected { ACCENT } else { TEXT };
        fill(
            Rectangle::new(Point::new(0, y), Size::new(WIDTH - 1, ROW_HEIGHT as u32)),
            BACKGROUND,
            target,
        )?;
        if row.selected {
            fill(
                Rectangle::new(Point::new(0, y + 1), Size::new(1, 6)),
                ACCENT,
                target,
            )?;
        }
        draw_kind(row.kind, Point::new(2, y + 1), row_text, target)?;
        draw_bounded(row.label, Point::new(10, y + 1), 11, row_text, target)?;
    }

    draw_scroll_marker(
        view.position,
        view.total,
        view.rows.len().min(VISIBLE_ROWS),
        target,
    )
}

fn fill<D: DrawTarget<Color = Rgb565>>(
    rectangle: Rectangle,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    rectangle
        .into_styled(PrimitiveStyle::with_fill(color))
        .draw(target)
}

fn draw_text<D: DrawTarget<Color = Rgb565>>(
    value: &str,
    point: Point,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    Text::with_baseline(
        value,
        point,
        MonoTextStyle::new(&FONT_4X6, color),
        Baseline::Top,
    )
    .draw(target)?;
    Ok(())
}

/// Draws at most `max_glyphs` input characters. Long labels get a three-dot
/// suffix while staying inside the fixed-width row. The scans stop after the
/// visible prefix, even if a caller supplies an unusually long string.
fn draw_bounded<D: DrawTarget<Color = Rgb565>>(
    value: &str,
    point: Point,
    max_glyphs: usize,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    let Some((truncation_byte, _)) = value.char_indices().nth(max_glyphs) else {
        return draw_text(value, point, color, target);
    };

    let prefix_glyphs = max_glyphs.saturating_sub(3);
    let prefix_end = value
        .char_indices()
        .nth(prefix_glyphs)
        .map_or(truncation_byte, |(byte, _)| byte);
    let prefix = &value[..prefix_end];
    draw_text(prefix, point, color, target)?;
    draw_text(
        "...",
        Point::new(point.x + prefix_glyphs as i32 * 4, point.y),
        color,
        target,
    )
}

fn draw_kind<D: DrawTarget<Color = Rgb565>>(
    kind: EntryKind,
    point: Point,
    color: Rgb565,
    target: &mut D,
) -> Result<(), D::Error> {
    match kind {
        EntryKind::Action => fill(
            Rectangle::new(Point::new(point.x + 1, point.y + 2), Size::new(3, 3)),
            color,
            target,
        ),
        EntryKind::Folder => {
            // A tiny tabbed outline with an unlit centre in every row.
            fill(
                Rectangle::new(Point::new(point.x, point.y + 1), Size::new(3, 1)),
                color,
                target,
            )?;
            fill(
                Rectangle::new(Point::new(point.x, point.y + 2), Size::new(5, 3)),
                color,
                target,
            )?;
            fill(
                Rectangle::new(Point::new(point.x + 1, point.y + 3), Size::new(3, 1)),
                BACKGROUND,
                target,
            )
        }
    }
}

fn draw_scroll_marker<D: DrawTarget<Color = Rgb565>>(
    position: usize,
    total: usize,
    visible: usize,
    target: &mut D,
) -> Result<(), D::Error> {
    let track = Rectangle::new(
        Point::new(SCROLL_X, SCROLL_TOP),
        Size::new(1, SCROLL_HEIGHT as u32),
    );
    fill(track, SCROLL_TRACK, target)?;
    if total == 0 {
        return Ok(());
    }

    let thumb_height = ((SCROLL_HEIGHT as usize * visible.min(total)) / total)
        .clamp(3, SCROLL_HEIGHT as usize) as i32;
    let travel = SCROLL_HEIGHT - thumb_height;
    let max_position = total.saturating_sub(1).max(1);
    let thumb_top = SCROLL_TOP
        + ((travel as u128 * position.min(max_position) as u128) / max_position as u128) as i32;
    fill(
        Rectangle::new(
            Point::new(SCROLL_X, thumb_top),
            Size::new(1, thumb_height as u32),
        ),
        ACCENT,
        target,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Frame([Rgb565; (WIDTH * HEIGHT) as usize]);

    impl Default for Frame {
        fn default() -> Self {
            Self([BACKGROUND; (WIDTH * HEIGHT) as usize])
        }
    }

    impl DrawTarget for Frame {
        type Color = Rgb565;
        type Error = core::convert::Infallible;

        fn draw_iter<I>(&mut self, pixels: I) -> Result<(), Self::Error>
        where
            I: IntoIterator<Item = Pixel<Self::Color>>,
        {
            for Pixel(point, color) in pixels {
                if point.x >= 0 && point.x < WIDTH as i32 && point.y >= 0 && point.y < HEIGHT as i32
                {
                    self.0[point.y as usize * WIDTH as usize + point.x as usize] = color;
                }
            }
            Ok(())
        }
    }

    impl OriginDimensions for Frame {
        fn size(&self) -> Size {
            Size::new(WIDTH, HEIGHT)
        }
    }

    struct FailingFrame {
        draw_calls: usize,
        fail_at: usize,
    }

    impl DrawTarget for FailingFrame {
        type Color = Rgb565;
        type Error = &'static str;

        fn draw_iter<I>(&mut self, _pixels: I) -> Result<(), Self::Error>
        where
            I: IntoIterator<Item = Pixel<Self::Color>>,
        {
            if self.draw_calls == self.fail_at {
                return Err("draw failed");
            }
            self.draw_calls += 1;
            Ok(())
        }
    }

    impl OriginDimensions for FailingFrame {
        fn size(&self) -> Size {
            Size::new(WIDTH, HEIGHT)
        }
    }

    #[test]
    fn selection_keeps_row_background_and_title_ink_black() {
        let rows = [MenuRow {
            label: "Start",
            kind: EntryKind::Action,
            selected: true,
        }];
        let mut frame = Frame::default();
        render(
            MenuView {
                title: "GAMES",
                rows: &rows,
                position: 0,
                total: 1,
            },
            &mut frame,
        )
        .unwrap();

        assert_eq!(frame.0[8 * WIDTH as usize], Rgb565::BLACK);
        assert_eq!(frame.0[9 * WIDTH as usize], ACCENT);
        for y in HEADER_HEIGHT as usize..HEIGHT as usize {
            for x in 54..63 {
                assert_eq!(frame.0[y * WIDTH as usize + x], Rgb565::BLACK);
            }
        }
        assert_eq!(frame.0[9 * WIDTH as usize + 63], ACCENT);
        assert_eq!(frame.0[9 * WIDTH as usize + 11], ACCENT);
        let header = &frame.0[..7 * WIDTH as usize];
        assert!(header.contains(&TITLE_TEXT));
        assert!(!header.contains(&Rgb565::WHITE));
    }

    #[test]
    fn long_unicode_labels_are_safely_clipped_to_visible_prefix() {
        let mut frame = Frame::default();
        draw_bounded(
            "界界界界界界界界界界界界界界界界",
            Point::new(10, 9),
            11,
            TEXT,
            &mut frame,
        )
        .unwrap();
        assert_eq!(frame.0[9 * WIDTH as usize + 10], TEXT);
        assert!(frame.0[9 * WIDTH as usize + 62] == BACKGROUND);
    }

    #[test]
    fn a_thousand_rows_draw_exactly_the_same_three_row_viewport() {
        let first = [
            MenuRow {
                label: "Names",
                kind: EntryKind::Action,
                selected: false,
            },
            MenuRow {
                label: "Watch",
                kind: EntryKind::Folder,
                selected: true,
            },
            MenuRow {
                label: "Play",
                kind: EntryKind::Folder,
                selected: false,
            },
        ];
        let mut many = [first[0]; 1_000];
        many[..first.len()].copy_from_slice(&first);
        let mut short_frame = Frame::default();
        let mut long_frame = Frame::default();

        render(
            MenuView {
                title: "DISPLAITOR",
                rows: &first,
                position: 1,
                total: 1_000,
            },
            &mut short_frame,
        )
        .unwrap();
        render(
            MenuView {
                title: "DISPLAITOR",
                rows: &many,
                position: 1,
                total: 1_000,
            },
            &mut long_frame,
        )
        .unwrap();

        assert_eq!(short_frame.0, long_frame.0);
    }

    #[test]
    fn ten_thousand_character_label_draws_the_same_clipped_pixels() {
        let mut long = [b'x'; 10_000];
        long[..8].copy_from_slice(b"abcdefgh");
        let long = core::str::from_utf8(&long).unwrap();
        let mut long_frame = Frame::default();
        let mut short_frame = Frame::default();

        draw_bounded(long, Point::new(10, 9), 11, TEXT, &mut long_frame).unwrap();
        draw_bounded(
            "abcdefgh12345",
            Point::new(10, 9),
            11,
            TEXT,
            &mut short_frame,
        )
        .unwrap();

        assert_eq!(long_frame.0, short_frame.0);
    }

    #[test]
    fn renderer_propagates_a_drawing_error_after_clear() {
        let rows = [MenuRow {
            label: "Start",
            kind: EntryKind::Action,
            selected: true,
        }];
        let mut target = FailingFrame {
            draw_calls: 0,
            fail_at: 1,
        };

        assert_eq!(
            render(
                MenuView {
                    title: "GAMES",
                    rows: &rows,
                    position: 0,
                    total: 1,
                },
                &mut target,
            ),
            Err("draw failed")
        );
    }

    #[test]
    fn scroll_marker_clamps_out_of_range_positions() {
        let mut frame = Frame::default();
        draw_scroll_marker(usize::MAX, usize::MAX, 3, &mut frame).unwrap();
        assert_eq!(
            frame.0[SCROLL_TOP as usize * WIDTH as usize + SCROLL_X as usize],
            SCROLL_TRACK
        );
        assert_eq!(
            frame.0[(HEIGHT as usize - 1) * WIDTH as usize + SCROLL_X as usize],
            ACCENT
        );
    }
}
