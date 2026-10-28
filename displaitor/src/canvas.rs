//! Retained background and indexed text layers. All storage and draw work are bounded.
use embedded_graphics::{
    mono_font::{
        MonoFont, MonoTextStyle,
        iso_8859_1::{FONT_4X6, FONT_6X10, FONT_10X20},
    },
    pixelcolor::{Rgb565, raw::RawU16},
    prelude::*,
    primitives::{PrimitiveStyle, Rectangle},
    text::{Baseline, Text},
};

use crate::{AudioId, HEIGHT, WIDTH};

pub const MAX_SLOTS: usize = 8;
pub const MAX_TEXT: usize = 64;
pub const FRAME_BYTES: usize = (WIDTH * HEIGHT * 2) as usize;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Error {
    Packet = 1,
    Version = 2,
    Command = 3,
    Value = 4,
    Layout = 5,
    Text = 6,
    Transaction = 7,
}

#[derive(Clone, Copy)]
struct Slot {
    enabled: bool,
    x: u8,
    y: u8,
    width: u8,
    height: u8,
    font: u8,
    foreground: u16,
    background: Option<u16>,
    text: [u8; MAX_TEXT],
    len: u8,
}

impl Slot {
    const EMPTY: Self = Self {
        enabled: false,
        x: 0,
        y: 0,
        width: 1,
        height: 1,
        font: 0,
        foreground: 0xffff,
        background: None,
        text: [0; MAX_TEXT],
        len: 0,
    };

    fn set_text(&mut self, bytes: &[u8]) -> Result<(), Error> {
        if bytes.len() > MAX_TEXT {
            return Err(Error::Text);
        }
        let text = core::str::from_utf8(bytes).map_err(|_| Error::Text)?;
        if !text
            .chars()
            .all(|c| matches!(c, ' '..='~' | '\u{a0}'..='\u{ff}'))
        {
            return Err(Error::Text);
        }
        self.text[..bytes.len()].copy_from_slice(bytes);
        self.len = bytes.len() as u8;
        Ok(())
    }
}

#[derive(Clone, Copy)]
struct Scene {
    background: [u16; FRAME_BYTES / 2],
    slots: [Slot; MAX_SLOTS],
    layout: u32,
    has_scene: bool,
}

pub struct Canvas {
    input: crate::canvas_input::ButtonHistory,
    visible: Scene,
    staged: Scene,
    transaction: bool,
    failed: bool,
    changed: bool,
    deferred_show: bool,
    show_ready: bool,
    deferred_audio: Option<AudioId>,
    audio_ready: Option<AudioId>,
    dirty: bool,
}

impl Default for Canvas {
    fn default() -> Self {
        Self::new()
    }
}

impl Canvas {
    pub const fn new() -> Self {
        Self {
            input: crate::canvas_input::ButtonHistory::new(),
            visible: Scene::new(),
            staged: Scene::new(),
            transaction: false,
            failed: false,
            changed: false,
            deferred_show: false,
            show_ready: false,
            deferred_audio: None,
            audio_ready: None,
            dirty: true,
        }
    }
    /// The scene currently visible on the display.
    pub const fn layout_id(&self) -> u32 {
        self.visible.layout
    }

    /// Read a baseline or events after a cursor without consuming input history.
    pub fn buttons(&self, after_id: Option<u32>) -> crate::canvas_input::ButtonsReport {
        self.input.read(after_id)
    }

    pub(crate) fn record_buttons(
        &mut self,
        elapsed: core::time::Duration,
        controls: crate::Controls,
        active: bool,
    ) {
        self.input.record(elapsed, controls, active);
    }

    /// Replies describe the scene targeted by subsequent mutation commands.
    pub const fn protocol_layout_id(&self) -> u32 {
        if self.transaction {
            self.staged.layout
        } else {
            self.visible.layout
        }
    }

    pub(crate) fn take_dirty(&mut self) -> bool {
        core::mem::take(&mut self.dirty)
    }
    pub(crate) fn take_show_request(&mut self) -> bool {
        core::mem::take(&mut self.show_ready)
    }
    pub(crate) fn take_audio_request(&mut self) -> Option<AudioId> {
        self.audio_ready.take()
    }
    pub(crate) fn fail_transaction(&mut self) {
        self.failed |= self.transaction;
    }

    /// Drop unpublished content and navigation on transport/session reset.
    pub fn abort_transaction(&mut self) {
        self.transaction = false;
        self.failed = false;
        self.changed = false;
        self.deferred_show = false;
        self.show_ready = false;
        self.deferred_audio = None;
        self.audio_ready = None;
    }

    /// Commands 7/8/9 begin, commit and abort a logical scene update.
    /// Begin replaces any abandoned transaction with a copy of the visible scene.
    /// Any rejected command poisons staging until a new Begin or Abort.
    pub fn apply(&mut self, command: u8, payload: &[u8]) -> Result<(), Error> {
        let result = self.apply_inner(command, payload);
        if result.is_err() {
            self.fail_transaction();
        }
        result
    }

    fn apply_inner(&mut self, command: u8, payload: &[u8]) -> Result<(), Error> {
        if matches!(command, 6..=9) && !payload.is_empty() {
            return Err(Error::Value);
        }
        match command {
            7 => {
                self.abort_transaction();
                self.staged = self.visible;
                self.transaction = true;
            }
            8 => {
                if !self.transaction || self.failed {
                    return Err(Error::Transaction);
                }
                core::mem::swap(&mut self.visible, &mut self.staged);
                self.dirty |= self.changed;
                self.show_ready = self.deferred_show;
                self.audio_ready = self.deferred_audio.take();
                self.transaction = false;
                self.changed = false;
                self.deferred_show = false;
            }
            9 => self.abort_transaction(),
            11 => {
                if self.failed {
                    return Err(Error::Transaction);
                }
                let [id] = payload else {
                    return Err(Error::Value);
                };
                let clip = AudioId::canvas_cry(*id).ok_or(Error::Value)?;
                if self.transaction {
                    self.deferred_audio = Some(clip);
                } else {
                    self.audio_ready = Some(clip);
                }
            }
            6 => {
                if self.failed {
                    return Err(Error::Transaction);
                }
                if self.transaction {
                    self.deferred_show = true;
                } else {
                    self.show_ready = true;
                }
            }
            _ => {
                if self.transaction && self.failed && command != 0 {
                    return Err(Error::Transaction);
                }
                let scene = if self.transaction {
                    &mut self.staged
                } else {
                    &mut self.visible
                };
                scene.apply(command, payload)?;
                if command != 0 {
                    if self.transaction {
                        self.changed = true;
                    } else {
                        self.dirty = true;
                    }
                }
            }
        }
        Ok(())
    }

    pub fn render<D: DrawTarget<Color = Rgb565>>(&self, target: &mut D) -> Result<(), D::Error> {
        self.visible.render(target)
    }
}

impl Scene {
    const fn new() -> Self {
        Self {
            background: [0; FRAME_BYTES / 2],
            slots: [Slot::EMPTY; MAX_SLOTS],
            layout: 0,
            has_scene: false,
        }
    }

    /// Apply one validated protocol command atomically. Invalid data leaves the scene intact.
    /// 0: info, 1: RGB565 background, 2: layout, 3: text, 4: style, 5: solid background.
    pub fn apply(&mut self, command: u8, payload: &[u8]) -> Result<(), Error> {
        if payload.len() > FRAME_BYTES {
            return Err(Error::Value);
        }
        match command {
            0 if payload.is_empty() => return Ok(()),
            1 if payload.len() == FRAME_BYTES => {
                for (pixel, bytes) in self.background.iter_mut().zip(payload.as_chunks::<2>().0) {
                    *pixel = u16::from_le_bytes([bytes[0], bytes[1]]);
                }
            }
            2 => self.set_layout(payload)?,
            3 | 4 => {
                if payload.len() < 5 {
                    return Err(Error::Value);
                }
                if u32::from_le_bytes(payload[..4].try_into().unwrap()) != self.layout {
                    return Err(Error::Layout);
                }
                let slot = self
                    .slots
                    .get_mut(payload[4] as usize)
                    .filter(|s| s.enabled)
                    .ok_or(Error::Value)?;
                if command == 3 {
                    slot.set_text(&payload[5..])?;
                } else {
                    if payload.len() != 10 || payload[7] > 1 {
                        return Err(Error::Value);
                    }
                    slot.foreground = u16::from_le_bytes([payload[5], payload[6]]);
                    slot.background =
                        (payload[7] != 0).then(|| u16::from_le_bytes([payload[8], payload[9]]));
                }
            }
            5 if payload.len() == 2 => self
                .background
                .fill(u16::from_le_bytes([payload[0], payload[1]])),
            0 | 1 | 5 => return Err(Error::Value),
            _ => return Err(Error::Command),
        }
        self.has_scene = true;
        Ok(())
    }

    fn set_layout(&mut self, payload: &[u8]) -> Result<(), Error> {
        if payload.len() < 9 {
            return Err(Error::Value);
        }
        let id = u32::from_le_bytes(payload[..4].try_into().unwrap());
        if id != crate::canvas_protocol::crc32(&payload[4..]) {
            return Err(Error::Layout);
        }
        let count = payload[8] as usize;
        if count > MAX_SLOTS {
            return Err(Error::Value);
        }
        let mut slots = [Slot::EMPTY; MAX_SLOTS];
        let mut data = &payload[9..];
        for _ in 0..count {
            if data.len() < 12 {
                return Err(Error::Value);
            }
            let index = data[0] as usize;
            if index >= MAX_SLOTS
                || slots[index].enabled
                || data[1] >= WIDTH as u8
                || data[2] >= HEIGHT as u8
                || data[3] == 0
                || data[3] > WIDTH as u8 - data[1]
                || data[4] == 0
                || data[4] > HEIGHT as u8 - data[2]
                || data[5] > 2
                || data[8] > 1
            {
                return Err(Error::Value);
            }
            let len = data[11] as usize;
            if data.len() < 12 + len {
                return Err(Error::Value);
            }
            let mut slot = Slot {
                enabled: true,
                x: data[1],
                y: data[2],
                width: data[3],
                height: data[4],
                font: data[5],
                foreground: u16::from_le_bytes([data[6], data[7]]),
                background: (data[8] != 0).then(|| u16::from_le_bytes([data[9], data[10]])),
                ..Slot::EMPTY
            };
            slot.set_text(&data[12..12 + len])?;
            slots[index] = slot;
            data = &data[12 + len..];
        }
        if !data.is_empty() {
            return Err(Error::Value);
        }
        self.slots = slots;
        self.layout = id;
        Ok(())
    }

    pub fn render<D: DrawTarget<Color = Rgb565>>(&self, target: &mut D) -> Result<(), D::Error> {
        if !self.has_scene {
            target.fill_solid(
                &Rectangle::new(Point::zero(), Size::new(WIDTH, HEIGHT)),
                Rgb565::BLACK,
            )?;
            for (index, (line, color)) in [
                ("CANVAS", Rgb565::CYAN),
                ("USB TO PC", Rgb565::WHITE),
                ("RUN A SCRIPT", Rgb565::new(16, 32, 16)),
                ("tools/pc_hub.py", Rgb565::new(31, 40, 8)),
            ]
            .into_iter()
            .enumerate()
            {
                Text::with_baseline(
                    line,
                    Point::new(2, index as i32 * 8),
                    MonoTextStyle::new(&FONT_4X6, color),
                    Baseline::Top,
                )
                .draw(target)?;
            }
            return Ok(());
        }
        target.fill_contiguous(
            &Rectangle::new(Point::zero(), Size::new(WIDTH, HEIGHT)),
            self.background
                .iter()
                .copied()
                .map(|p| Rgb565::from(RawU16::new(p))),
        )?;
        // Slot order is the z order. No graph traversal or unbounded string rendering.
        for slot in &self.slots {
            if !slot.enabled {
                continue;
            }
            let area = Rectangle::new(
                Point::new(i32::from(slot.x), i32::from(slot.y)),
                Size::new(u32::from(slot.width), u32::from(slot.height)),
            );
            let mut clipped = target.clipped(&area);
            if let Some(color) = slot.background {
                area.into_styled(PrimitiveStyle::with_fill(Rgb565::from(RawU16::new(color))))
                    .draw(&mut clipped)?;
            }
            let font: &MonoFont<'_> = match slot.font {
                0 => &FONT_4X6,
                1 => &FONT_6X10,
                _ => &FONT_10X20,
            };
            let text =
                core::str::from_utf8(&slot.text[..slot.len as usize]).expect("validated text");
            Text::with_baseline(
                text,
                area.top_left,
                MonoTextStyle::new(font, Rgb565::from(RawU16::new(slot.foreground))),
                Baseline::Top,
            )
            .draw(&mut clipped)?;
        }
        Ok(())
    }
}
