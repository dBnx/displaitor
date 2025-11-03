use core::fmt::{self, Write};

/*
use spin::{Mutex, MutexGuard};
use critical_section::{CriticalSection, Mutex};

pub type GlobalFixedBuffer = FixedBuffer<128>;
static GLOBAL_BUFFER: Mutex<GlobalFixedBuffer> = Mutex::new(FixedBuffer::new());

pub struct MutexGuard<'a, T> {
    inner: &'a mut T,
    cs: CriticalSection<'a>,
}

pub fn get_global_buffer<'a>() -> MutexGuard<<'a, GlobalFixedBuffer> {
    let cs = CriticalSection::new();
    let v = GLOBAL_BUFFER.borrow();
    MutexGuard {
        inner: v,
        cs,
    }
}

pub fn get_global_buffer_cleared() -> spin::MutexGuard<'static, FixedBuffer<128>> {
    let mut buffer = get_global_buffer();
    buffer.clear();
    buffer
}
*/

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_creates_empty_buffer() {
        let buffer = FixedBuffer::<16>::new();
        assert_eq!(buffer.as_str(), "");
    }

    #[test]
    fn test_write_str_valid() {
        let mut buffer = FixedBuffer::<16>::new();
        assert!(buffer.write_str("hello").is_ok());
        assert_eq!(buffer.as_str(), "hello");
    }

    #[test]
    fn test_write_str_multiple() {
        let mut buffer = FixedBuffer::<16>::new();
        assert!(buffer.write_str("hello").is_ok());
        assert!(buffer.write_str(" ").is_ok());
        assert!(buffer.write_str("world").is_ok());
        assert_eq!(buffer.as_str(), "hello world");
    }

    #[test]
    fn test_write_str_overflow() {
        let mut buffer = FixedBuffer::<5>::new();
        assert!(buffer.write_str("hello").is_ok());
        assert!(buffer.write_str("x").is_err());
    }

    #[test]
    fn test_write_str_exact_capacity() {
        let mut buffer = FixedBuffer::<5>::new();
        assert!(buffer.write_str("hello").is_ok());
        assert_eq!(buffer.as_str(), "hello");
    }

    #[test]
    fn test_clear() {
        let mut buffer = FixedBuffer::<16>::new();
        assert!(buffer.write_str("hello").is_ok());
        assert_eq!(buffer.as_str(), "hello");
        buffer.clear();
        assert_eq!(buffer.as_str(), "");
    }

    #[test]
    fn test_clear_then_write() {
        let mut buffer = FixedBuffer::<16>::new();
        assert!(buffer.write_str("hello").is_ok());
        buffer.clear();
        assert!(buffer.write_str("world").is_ok());
        assert_eq!(buffer.as_str(), "world");
    }

    #[test]
    fn test_as_str_empty() {
        let buffer = FixedBuffer::<16>::new();
        assert_eq!(buffer.as_str(), "");
    }
}

/*
use core::fmt::{self, Write};
use critical_section::Mutex;
use core::cell::RefCell;

static GLOBAL_BUFFER: Mutex<RefCell<FixedBuffer<128>>> = Mutex::new(RefCell::new(FixedBuffer::new()));

pub struct CriticalSectionGuard<'a, T> {
    data: critical_section::MutexGuard<'a, RefCell<T>>,
}

impl<'a, T> core::ops::Deref for CriticalSectionGuard<'a, T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        &self.data.borrow()
    }
}

impl<'a, T> core::ops::DerefMut for CriticalSectionGuard<'a, T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.data.borrow_mut()
    }
}

pub fn get_global_buffer() -> CriticalSectionGuard<'static, FixedBuffer<128>> {
    critical_section::with(|cs| CriticalSectionGuard {
        data: GLOBAL_BUFFER.borrow(cs),
    })
}

pub fn get_global_buffer_cleared() -> CriticalSectionGuard<'static, FixedBuffer<128>> {
    let mut buffer = get_global_buffer();
    buffer.clear();
    buffer
}

pub struct FixedBuffer<const N: usize> {
    buffer: [u8; N],
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
 */