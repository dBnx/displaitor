//! COBS-delimited, CRC32-checked stop-and-wait messages, shared by USB and simulator.
use crate::canvas::{Canvas, Error, FRAME_BYTES, MAX_SLOTS, MAX_TEXT};
use crate::canvas_input::ButtonsReport;

pub const MAX_PACKET: usize = FRAME_BYTES + 8;
pub const MAX_ENCODED: usize = MAX_PACKET + MAX_PACKET / 254 + 1;
pub const MAX_REPLY: usize = 62;

pub fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0_u32;
    for &byte in bytes {
        crc ^= u32::from(byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & 0_u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}

pub fn encode(bytes: &[u8], output: &mut [u8]) -> Option<usize> {
    if output.is_empty() {
        return None;
    }
    let mut code_pos = 0;
    let mut position = 1;
    let mut code = 1_u8;
    for &byte in bytes {
        if byte == 0 {
            *output.get_mut(code_pos)? = code;
            code_pos = position;
            position += 1;
            code = 1;
        } else {
            *output.get_mut(position)? = byte;
            position += 1;
            code += 1;
            if code == 255 {
                *output.get_mut(code_pos)? = code;
                code_pos = position;
                position += 1;
                code = 1;
            }
        }
    }
    *output.get_mut(code_pos)? = code;
    *output.get_mut(position)? = 0;
    Some(position + 1)
}

fn decode(bytes: &mut [u8]) -> Option<usize> {
    let mut read = 0;
    let mut write = 0;
    while read < bytes.len() {
        let code = bytes[read] as usize;
        read += 1;
        if code == 0 || read + code - 1 > bytes.len() {
            return None;
        }
        for _ in 1..code {
            bytes[write] = bytes[read];
            write += 1;
            read += 1;
        }
        if code != 255 && read < bytes.len() {
            bytes[write] = 0;
            write += 1;
        }
    }
    Some(write)
}

pub struct Receiver {
    bytes: [u8; MAX_ENCODED],
    len: usize,
    overflow: bool,
}

impl Default for Receiver {
    fn default() -> Self {
        Self::new()
    }
}
impl Receiver {
    pub const fn new() -> Self {
        Self {
            bytes: [0; MAX_ENCODED],
            len: 0,
            overflow: false,
        }
    }
    pub fn reset(&mut self) {
        self.len = 0;
        self.overflow = false;
    }

    pub fn feed(&mut self, byte: u8, canvas: &mut Canvas) -> Option<Reply> {
        if byte != 0 {
            if self.len < self.bytes.len() && !self.overflow {
                self.bytes[self.len] = byte;
                self.len += 1;
            } else {
                self.overflow = true;
            }
            return None;
        }
        if self.len == 0 && !self.overflow {
            return None;
        }
        let length = self.len;
        let overflow = self.overflow;
        self.reset();
        // Corrupt envelopes have no trustworthy sequence; sender recovers on timeout.
        if overflow {
            return None;
        }
        let len = decode(&mut self.bytes[..length])?;
        let packet = &self.bytes[..len];
        if !(8..=MAX_PACKET).contains(&len) {
            return None;
        }
        let end = len - 4;
        if crc32(&packet[..end]) != u32::from_le_bytes(packet[end..].try_into().ok()?) {
            return None;
        }
        let sequence = u16::from_le_bytes([packet[2], packet[3]]);
        let mut buttons = None;
        let result = if packet[0] != 1 {
            Err(Error::Version)
        } else if packet[1] == 10 {
            match &packet[4..end] {
                [] => {
                    buttons = Some(canvas.buttons(None));
                    Ok(())
                }
                [a, b, c, d] => {
                    buttons = Some(canvas.buttons(Some(u32::from_le_bytes([*a, *b, *c, *d]))));
                    Ok(())
                }
                _ => Err(Error::Value),
            }
        } else {
            canvas.apply(packet[1], &packet[4..end])
        };
        if result.is_err() {
            canvas.fail_transaction();
        }
        let show_canvas = canvas.take_show_request();
        Some(Reply {
            sequence,
            status: result.err().map_or(0, |error| error as u8),
            layout: canvas.protocol_layout_id(),
            show_canvas,
            buttons,
        })
    }
}

pub struct Reply {
    pub sequence: u16,
    pub status: u8,
    pub layout: u32,
    pub buttons: Option<ButtonsReport>,
    /// Local effect metadata, not part of the encoded reply.
    pub show_canvas: bool,
}
impl Reply {
    pub fn encode(&self, output: &mut [u8; MAX_REPLY]) -> usize {
        if let Some(buttons) = &self.buttons {
            let mut packet = [0_u8; 60];
            packet[..8].copy_from_slice(&[
                1,
                0x81,
                self.sequence as u8,
                (self.sequence >> 8) as u8,
                0,
                buttons.state,
                buttons.flags,
                buttons.count,
            ]);
            packet[8..12].copy_from_slice(&buttons.latest.to_le_bytes());
            packet[12..16].copy_from_slice(&buttons.overwritten.to_le_bytes());
            packet[16..20].copy_from_slice(&buttons.now_ms.to_le_bytes());
            let mut end = 20;
            for event in &buttons.events[..usize::from(buttons.count)] {
                packet[end..end + 4].copy_from_slice(&event.id.to_le_bytes());
                packet[end + 4..end + 8].copy_from_slice(&event.at_ms.to_le_bytes());
                packet[end + 8] = event.state;
                end += 9;
            }
            let crc = crc32(&packet[..end]);
            packet[end..end + 4].copy_from_slice(&crc.to_le_bytes());
            return encode(&packet[..end + 4], output).expect("bounded button reply fits");
        }
        let mut packet = [
            1,
            0x80,
            self.sequence as u8,
            (self.sequence >> 8) as u8,
            self.status,
            64,
            32,
            MAX_SLOTS as u8,
            MAX_TEXT as u8,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ];
        packet[9..13].copy_from_slice(&self.layout.to_le_bytes());
        let crc = crc32(&packet[..13]);
        packet[13..].copy_from_slice(&crc.to_le_bytes());
        encode(&packet, output).expect("fixed reply fits")
    }
}

/// One pending reply prevents reading another request until the adapter drains it.
pub struct Endpoint {
    receiver: Receiver,
    output: [u8; MAX_REPLY],
    start: usize,
    end: usize,
    show_requested: bool,
}
impl Default for Endpoint {
    fn default() -> Self {
        Self::new()
    }
}
impl Endpoint {
    pub const fn new() -> Self {
        Self {
            receiver: Receiver::new(),
            output: [0; MAX_REPLY],
            start: 0,
            end: 0,
            show_requested: false,
        }
    }
    pub fn reset(&mut self, canvas: &mut Canvas) {
        canvas.abort_transaction();
        self.receiver.reset();
        self.start = 0;
        self.end = 0;
        self.show_requested = false;
    }
    /// Consume a validated explicit activation; ordinary scene packets never navigate.
    pub fn take_show_request(&mut self) -> bool {
        core::mem::take(&mut self.show_requested)
    }
    pub fn pending(&self) -> &[u8] {
        &self.output[self.start..self.end]
    }
    pub fn written(&mut self, count: usize) {
        self.start += count.min(self.end - self.start);
    }
    /// Returns false if backpressure requires draining the reply first; byte was not consumed.
    pub fn receive(&mut self, byte: u8, canvas: &mut Canvas) -> bool {
        if !self.pending().is_empty() {
            return false;
        }
        if let Some(reply) = self.receiver.feed(byte, canvas) {
            self.show_requested |= reply.show_canvas;
            self.start = 0;
            self.end = reply.encode(&mut self.output);
        }
        true
    }
}
