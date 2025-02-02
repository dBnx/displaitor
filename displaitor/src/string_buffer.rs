use core::fmt::{self, Write};

use spin::{Mutex, MutexGuard};

static GLOBAL_BUFFER: Mutex<FixedBuffer<128>> = Mutex::new(FixedBuffer::new());

pub fn get_global_buffer() -> spin::MutexGuard<'static, FixedBuffer<128>> {
    GLOBAL_BUFFER.lock()
}

pub fn get_global_buffer_cleared() -> spin::MutexGuard<'static, FixedBuffer<128>> {
    let mut buffer = get_global_buffer();
    buffer.clear();
    buffer
}

pub struct FixedBuffer<const N: usize> {
    buffer: [u8; N], // Adjust size as needed
    pos: usize,
}

impl<const N: usize> FixedBuffer<N> {
    pub const fn new() -> Self {
        Self {
            buffer: [0; N],
            pos: 0,
        }
    }

    pub fn as_str(&self) -> &str {
        core::str::from_utf8(&self.buffer[..self.pos]).unwrap_or("")
    }

    pub fn clear(&mut self) {
        self.pos = 0;
    }
}

impl<const N: usize> Write for FixedBuffer<N> {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        let bytes = s.as_bytes();
        if self.pos + bytes.len() > self.buffer.len() {
            return Err(fmt::Error);
        }
        self.buffer[self.pos..self.pos + bytes.len()].copy_from_slice(bytes);
        self.pos += bytes.len();
        Ok(())
    }
}
