//! Flash-resident QOI atlas with a fixed-rate, deduplicated animation timeline.
//! Python owns the artwork; firmware borrows and decodes only the current frame.

use crate::AppId;

pub(crate) struct Clip {
    data: &'static [u8],
    ticks: usize,
    period_us: u64,
    table: usize,
    payload: usize,
}

const fn u16_at(data: &[u8], offset: usize) -> usize {
    u16::from_le_bytes([data[offset], data[offset + 1]]) as usize
}

const fn u32_at(data: &[u8], offset: usize) -> usize {
    u32::from_le_bytes([
        data[offset],
        data[offset + 1],
        data[offset + 2],
        data[offset + 3],
    ]) as usize
}

impl Clip {
    // Validate metadata at compile time, before any borrowed frame reaches the
    // decoder. No index scan, allocation or frame copying happens at startup.
    const fn new(data: &'static [u8]) -> Self {
        assert!(data.len() >= 12);
        assert!(data[0] == b'C' && data[1] == b'Z' && data[2] == b'Y' && data[3] == b'1');
        let ticks = u16_at(data, 4);
        let unique = u16_at(data, 6);
        assert!(unique > 0 && unique <= ticks);
        let period_us = u32_at(data, 8) as u64;
        assert!(period_us > 0);
        let table = 12 + ticks * 2;
        let payload = table + (unique + 1) * 4;
        assert!(payload <= data.len());
        let mut tick = 0;
        while tick < ticks {
            assert!(u16_at(data, 12 + tick * 2) < unique);
            tick += 1;
        }
        assert!(u32_at(data, table) == 0);
        let mut index = 0;
        while index < unique {
            let start = u32_at(data, table + index * 4);
            let end = u32_at(data, table + (index + 1) * 4);
            assert!(start < end && end <= data.len() - payload && end - start >= 22);
            let frame = payload + start;
            assert!(
                data[frame] == b'q'
                    && data[frame + 1] == b'o'
                    && data[frame + 2] == b'i'
                    && data[frame + 3] == b'f'
            );
            // QOI width and height are big endian; only native RGB frames ship.
            assert!(
                data[frame + 4] == 0
                    && data[frame + 5] == 0
                    && data[frame + 6] == 0
                    && data[frame + 7] == 64
            );
            assert!(
                data[frame + 8] == 0
                    && data[frame + 9] == 0
                    && data[frame + 10] == 0
                    && data[frame + 11] == 32
                    && data[frame + 12] == 3
            );
            index += 1;
        }
        assert!(u32_at(data, table + unique * 4) == data.len() - payload);
        Self {
            data,
            ticks,
            period_us,
            table,
            payload,
        }
    }

    pub(crate) const fn len(&self) -> usize {
        self.ticks
    }

    pub(crate) const fn period_us(&self) -> u64 {
        self.period_us
    }

    pub(crate) fn frame_id(&self, tick: usize) -> usize {
        u16_at(self.data, 12 + tick % self.ticks * 2)
    }

    pub(crate) fn frame(&self, tick: usize) -> &'static [u8] {
        let index = self.frame_id(tick);
        let start = self.payload + u32_at(self.data, self.table + index * 4);
        let end = self.payload + u32_at(self.data, self.table + (index + 1) * 4);
        &self.data[start..end]
    }
}

static FARM: Clip = Clip::new(include_bytes!("../assets/cozy/farm.cqoi"));
static WINTER: Clip = Clip::new(include_bytes!("../assets/cozy/winter.cqoi"));

static OKAMI: Clip = Clip::new(include_bytes!("../assets/cozy/okami.cqoi"));
static WITCHER: Clip = Clip::new(include_bytes!("../assets/cozy/witcher.cqoi"));
static REEF: Clip = Clip::new(include_bytes!("../assets/cozy/reef.cqoi"));
static FIRE: Clip = Clip::new(include_bytes!("../assets/cozy/fire.cqoi"));

static PALICO: Clip = Clip::new(include_bytes!("../assets/cozy/palico.cqoi"));

static RATHALOS: Clip = Clip::new(include_bytes!("../assets/cozy/rathalos.cqoi"));

static ZINOGRE: Clip = Clip::new(include_bytes!("../assets/cozy/zinogre.cqoi"));

static POOGIE: Clip = Clip::new(include_bytes!("../assets/cozy/poogie.cqoi"));

// Same order as the Python scene registry. A bounded ten-element scan runs only
// on a button edge; playback borrows a single compressed frame directly in Flash.
const SCENES: [AppId; 10] = [
    AppId::CozyFarm,
    AppId::CozyWinter,
    AppId::CozyOkami,
    AppId::CozyWitcher,
    AppId::CozyReef,
    AppId::Fire,
    AppId::CozyPalico,
    AppId::CozyRathalos,
    AppId::CozyZinogre,
    AppId::CozyPoogie,
];

pub(crate) fn adjacent(app: AppId, forward: bool) -> AppId {
    let index = SCENES
        .iter()
        .position(|&id| id == app)
        .expect("cozy application");
    let step = if forward { 1 } else { SCENES.len() - 1 };
    SCENES[(index + step) % SCENES.len()]
}

pub(crate) fn clip(app: AppId) -> &'static Clip {
    match app {
        AppId::CozyFarm => &FARM,
        AppId::CozyWinter => &WINTER,
        AppId::CozyOkami => &OKAMI,
        AppId::CozyWitcher => &WITCHER,
        AppId::CozyReef => &REEF,
        AppId::CozyPalico => &PALICO,
        AppId::CozyRathalos => &RATHALOS,
        AppId::CozyZinogre => &ZINOGRE,
        AppId::CozyPoogie => &POOGIE,
        AppId::Fire => &FIRE,
        _ => unreachable!("only cozy applications have a cozy clip"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
    use tinyqoi::Qoi;

    #[test]
    fn every_tick_decodes_to_the_python_rgb565_reference() {
        for (clip, expected) in [
            (&FARM, &include_bytes!("../assets/cozy/farm.hashes")[..]),
            (&WINTER, &include_bytes!("../assets/cozy/winter.hashes")[..]),
            (&OKAMI, &include_bytes!("../assets/cozy/okami.hashes")[..]),
            (
                &WITCHER,
                &include_bytes!("../assets/cozy/witcher.hashes")[..],
            ),
            (&REEF, &include_bytes!("../assets/cozy/reef.hashes")[..]),
            (&PALICO, &include_bytes!("../assets/cozy/palico.hashes")[..]),
            (
                &RATHALOS,
                &include_bytes!("../assets/cozy/rathalos.hashes")[..],
            ),
            (
                &ZINOGRE,
                &include_bytes!("../assets/cozy/zinogre.hashes")[..],
            ),
            (&POOGIE, &include_bytes!("../assets/cozy/poogie.hashes")[..]),
            (&FIRE, &include_bytes!("../assets/cozy/fire.hashes")[..]),
        ] {
            assert_eq!(expected.len(), clip.len() * 8);
            for tick in 0..clip.len() {
                let image = Qoi::new(clip.frame(tick)).unwrap();
                assert_eq!(image.size(), Size::new(64, 32));
                let mut hash = 0xcbf29ce484222325_u64;
                let mut count = 0;
                for color in image.pixels().take(2048) {
                    let raw = Rgb565::from(color).into_storage();
                    for byte in raw.to_le_bytes() {
                        hash = (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3);
                    }
                    count += 1;
                }
                assert_eq!(count, 2048);
                let expected =
                    u64::from_le_bytes(expected[tick * 8..tick * 8 + 8].try_into().unwrap());
                assert_eq!(hash, expected, "tick {tick}");
                assert_eq!(clip.frame(tick), clip.frame(tick + clip.len()));
            }
        }
    }
}

/// Sparse action overlays share the existing back buffer and never copy a clip.
/// Metadata and every run are checked at compile time, including pixel bounds.
pub(crate) struct ActionClip(&'static [u8]);

pub(crate) const ACTION_PERIOD_US: u64 = 100_000;
pub(crate) const ACTION_DURATION_US: u64 = 3_200_000;

impl ActionClip {
    const fn new(data: &'static [u8]) -> Self {
        assert!(data.len() >= 8);
        assert!(data[0] == b'A' && data[1] == b'C' && data[2] == b'T' && data[3] == b'1');
        let frames = u16_at(data, 4);
        assert!(frames as u64 * ACTION_PERIOD_US == ACTION_DURATION_US);
        assert!(u16_at(data, 6) as u64 * 1000 == ACTION_PERIOD_US);
        let payload = 8 + (frames + 1) * 4;
        assert!(payload <= data.len() && u32_at(data, 8) == 0);
        let mut frame = 0;
        while frame < frames {
            let start = u32_at(data, 8 + frame * 4);
            let end = u32_at(data, 12 + frame * 4);
            assert!(start <= end && end <= data.len() - payload);
            let mut cursor = payload + start;
            let mut previous = 0;
            while cursor < payload + end {
                assert!(cursor + 4 <= payload + end);
                let pixel = u16_at(data, cursor);
                let count = u16_at(data, cursor + 2);
                assert!(count > 0 && pixel >= previous && pixel + count <= 2048);
                previous = pixel + count;
                cursor += 4 + count * 2;
                assert!(cursor <= payload + end);
            }
            frame += 1;
        }
        assert!(u32_at(data, 8 + frames * 4) == data.len() - payload);
        Self(data)
    }

    pub(crate) fn draw<
        D: embedded_graphics::draw_target::DrawTarget<Color = embedded_graphics::pixelcolor::Rgb565>,
    >(
        &self,
        tick: usize,
        target: &mut D,
    ) -> Result<(), D::Error> {
        use embedded_graphics::{
            Pixel,
            geometry::Point,
            pixelcolor::{Rgb565, raw::RawU16},
        };
        let frames = u16_at(self.0, 4);
        if tick >= frames {
            return Ok(());
        }
        let payload = 8 + (frames + 1) * 4;
        let mut cursor = payload + u32_at(self.0, 8 + tick * 4);
        let end = payload + u32_at(self.0, 12 + tick * 4);
        while cursor < end {
            let start = u16_at(self.0, cursor);
            let count = u16_at(self.0, cursor + 2);
            cursor += 4;
            target.draw_iter((0..count).map(|index| {
                let position = start + index;
                Pixel(
                    Point::new((position % 64) as i32, (position / 64) as i32),
                    Rgb565::from(RawU16::new(u16_at(self.0, cursor + index * 2) as u16)),
                )
            }))?;
            cursor += count * 2;
        }
        Ok(())
    }
}

pub(crate) fn action(app: AppId) -> &'static ActionClip {
    static FARM: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/farm.action"));
    static WINTER: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/winter.action"));
    static OKAMI: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/okami.action"));
    static WITCHER: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/witcher.action"));
    static REEF: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/reef.action"));
    static FIRE: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/fire.action"));
    static PALICO: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/palico.action"));
    static RATHALOS: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/rathalos.action"));
    static ZINOGRE: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/zinogre.action"));
    static POOGIE: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/poogie.action"));
    static NYAN: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/nyan.action"));
    static HYPER: ActionClip = ActionClip::new(include_bytes!("../assets/cozy/hyper.action"));
    match app {
        AppId::Nyan => &NYAN,
        AppId::Hyper => &HYPER,
        AppId::CozyFarm => &FARM,
        AppId::CozyWinter => &WINTER,
        AppId::CozyOkami => &OKAMI,
        AppId::CozyWitcher => &WITCHER,
        AppId::CozyReef => &REEF,
        AppId::CozyPalico => &PALICO,
        AppId::CozyRathalos => &RATHALOS,
        AppId::CozyZinogre => &ZINOGRE,
        AppId::CozyPoogie => &POOGIE,
        AppId::Fire => &FIRE,
        _ => unreachable!("only cozy applications have an action clip"),
    }
}

#[cfg(test)]
mod action_tests {
    use super::*;
    use core::convert::Infallible;
    use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
    use tinyqoi::Qoi;

    struct Frame([Rgb565; 2048]);
    impl OriginDimensions for Frame {
        fn size(&self) -> Size {
            Size::new(64, 32)
        }
    }
    impl DrawTarget for Frame {
        type Color = Rgb565;
        type Error = Infallible;
        fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
            &mut self,
            pixels: I,
        ) -> Result<(), Self::Error> {
            for Pixel(p, c) in pixels {
                assert!((0..64).contains(&p.x) && (0..32).contains(&p.y));
                self.0[p.y as usize * 64 + p.x as usize] = c;
            }
            Ok(())
        }
    }
    #[test]
    fn sparse_actions_match_python_composites_on_every_tick() {
        for (app, hashes) in [
            (
                AppId::CozyPoogie,
                &include_bytes!("../assets/cozy/poogie.action-hashes")[..],
            ),
            (
                AppId::CozyZinogre,
                &include_bytes!("../assets/cozy/zinogre.action-hashes")[..],
            ),
            (
                AppId::CozyRathalos,
                &include_bytes!("../assets/cozy/rathalos.action-hashes")[..],
            ),
            (
                AppId::CozyPalico,
                &include_bytes!("../assets/cozy/palico.action-hashes")[..],
            ),
            (
                AppId::CozyFarm,
                &include_bytes!("../assets/cozy/farm.action-hashes")[..],
            ),
            (
                AppId::CozyWinter,
                &include_bytes!("../assets/cozy/winter.action-hashes")[..],
            ),
            (
                AppId::CozyOkami,
                &include_bytes!("../assets/cozy/okami.action-hashes")[..],
            ),
            (
                AppId::CozyWitcher,
                &include_bytes!("../assets/cozy/witcher.action-hashes")[..],
            ),
            (
                AppId::CozyReef,
                &include_bytes!("../assets/cozy/reef.action-hashes")[..],
            ),
            (
                AppId::Fire,
                &include_bytes!("../assets/cozy/fire.action-hashes")[..],
            ),
        ] {
            assert_eq!(hashes.len(), 32 * 8);
            for tick in 0..32 {
                let mut target = Frame([Rgb565::BLACK; 2048]);
                for (out, color) in target
                    .0
                    .iter_mut()
                    .zip(Qoi::new(clip(app).frame(15)).unwrap().pixels())
                {
                    *out = color.into();
                }
                action(app).draw(tick, &mut target).unwrap();
                let hash = target.0.iter().fold(0xcbf29ce484222325_u64, |hash, color| {
                    color
                        .into_storage()
                        .to_le_bytes()
                        .iter()
                        .fold(hash, |h, &b| (h ^ u64::from(b)).wrapping_mul(0x100000001b3))
                });
                assert_eq!(
                    hash,
                    u64::from_le_bytes(hashes[tick * 8..tick * 8 + 8].try_into().unwrap()),
                    "{app:?} tick {tick}"
                );
            }
        }
    }
}
