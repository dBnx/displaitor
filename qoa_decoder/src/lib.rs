#![no_std]

mod lms;
use lms::Lms;

use core::convert::TryInto;

#[derive(Debug)]
pub enum QoaError {
    InvalidFormat(&'static str),
    UnexpectedEof,
}

pub type Result<T> = core::result::Result<T, QoaError>;

/// Credit to qoaudio. This little LUT is simpler and faster than what I attempted.
const QOA_DEQUANT_TAB: [[i32; 8]; 16] = [
    [1, -1, 3, -3, 5, -5, 7, -7],
    [5, -5, 18, -18, 32, -32, 49, -49],
    [16, -16, 53, -53, 95, -95, 147, -147],
    [34, -34, 113, -113, 203, -203, 315, -315],
    [63, -63, 210, -210, 378, -378, 588, -588],
    [104, -104, 345, -345, 621, -621, 966, -966],
    [158, -158, 528, -528, 950, -950, 1477, -1477],
    [228, -228, 760, -760, 1368, -1368, 2128, -2128],
    [316, -316, 1053, -1053, 1895, -1895, 2947, -2947],
    [422, -422, 1405, -1405, 2529, -2529, 3934, -3934],
    [548, -548, 1828, -1828, 3290, -3290, 5117, -5117],
    [696, -696, 2320, -2320, 4176, -4176, 6496, -6496],
    [868, -868, 2893, -2893, 5207, -5207, 8099, -8099],
    [1064, -1064, 3548, -3548, 6386, -6386, 9933, -9933],
    [1286, -1286, 4288, -4288, 7718, -7718, 12005, -12005],
    [1536, -1536, 5120, -5120, 9216, -9216, 14336, -14336],
];



/// Decoder for the QOA format (mono, non-streaming).
/// It reads the file header, then frame headers and decodes slices of 20 samples.
pub struct QoaDecoder<'a> {
    data: &'a [u8],
    pos: usize,             // Current file offset.
    total_samples: u32,     // Total samples per channel (from file header).
    samples_read: u32,      // Number of samples returned so far.
    pub sample_rate: u32,   // Sample rate from the first frame header.

    // Current frame state.
    frame_samples_remaining: u32, // Samples remaining in the current frame.
    slices_in_frame: u32,         // Total slices in the current frame.
    current_slice_index: u32,     // Slices decoded so far in this frame.

    // Buffer for the current slice (up to 20 samples).
    slice_buffer: [i16; 20],
    slice_buffer_index: usize,    // Next sample index in the buffer.
    slice_buffer_len: usize,      // Number of valid samples in the current slice.

    // Mono channel LMS state.
    lms: Lms,
}

impl<'a> QoaDecoder<'a> {
    /// Creates a new QOA decoder by parsing the file header and the first frame.
    /// Returns an error if the header is truncated or the magic header is invalid.
    pub fn new(data: &'a [u8]) -> Result<Self> {
        if data.len() < 8 {
            return Err(QoaError::UnexpectedEof);
        }
        if &data[0..4] != b"qoaf" {
            return Err(QoaError::InvalidFormat("Invalid magic header"));
        }
        let total_samples = u32::from_be_bytes(data[4..8].try_into().unwrap());
        let mut decoder = QoaDecoder {
            data,
            pos: 8,
            total_samples,
            samples_read: 0,
            sample_rate: 0,
            frame_samples_remaining: 0,
            slices_in_frame: 0,
            current_slice_index: 0,
            slice_buffer: [0; 20],
            slice_buffer_index: 20, // Buffer initially empty.
            slice_buffer_len: 0,
            lms: Lms::new(),
        };
        decoder.load_next_frame()?;
        Ok(decoder)
    }

    /// Returns the number of samples per channel in the file.
    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }

    /// Returns the next decoded sample as an i16, or None if all samples have been returned.
    pub fn next_sample(&mut self) -> Option<i16> {
        if self.samples_read >= self.total_samples {
            return None;
        }
        // If the current slice buffer is exhausted, decode the next slice.
        if self.slice_buffer_index >= self.slice_buffer_len {
            if self.current_slice_index < self.slices_in_frame {
                if self.pos + 8 > self.data.len() {
                    return None;
                }

                let slice_bytes = &self.data[self.pos..self.pos + 8];
                self.pos += 8;
                self.current_slice_index += 1;
                let slice_val = u64::from_be_bytes(slice_bytes.try_into().unwrap());

                // let scale_factor = ((slice_val >> 60) & 0xF) as usize;
                // let quantized = ((slice_val >> 57) & 0x7) as usize;
                // let dequantized = QOA_DEQUANT_TAB[scale_factor][quantized];

                // let prediction = self.lms[channel_idx].predict();
                // let reconstructed = (prediction + dequantized).clamp(-32768, 32767) as i16;

                // let prediction = self.lms.predict();
                // let sample = (prediction + dequantized).clamp(-32768, 32767) as i16;
                // self.lms.update(sample, dequantized);

                let scale_factor = ((slice_val >> 60) & 0xF) as usize;
                let mut decoded = [0i16; 20];
                for i in 0..20 {
                    let shift = 60 - 3 * (i + 1);
                    let qr = ((slice_val >> shift) & 0x7) as usize;
                    let r = QOA_DEQUANT_TAB[scale_factor][qr];

                    let p = self.lms.predict();
                    let s = (p + r).clamp(-32768, 32767) as i16;
                    decoded[i] = s;
                    self.lms.update(s, r);
                }

                let slice_samples = if self.frame_samples_remaining < 20 {
                    self.frame_samples_remaining as usize
                } else {
                    20
                };

                self.slice_buffer = decoded;
                self.slice_buffer_index = 0;
                self.slice_buffer_len = slice_samples;
                self.frame_samples_remaining -= slice_samples as u32;
            } else {
                // End of frame; attempt to load the next frame.
                if self.pos >= self.data.len() || self.load_next_frame().is_err() {
                    return None;
                }
                return self.next_sample();
            }
        }
        let sample = self.slice_buffer[self.slice_buffer_index];
        self.slice_buffer_index += 1;
        self.samples_read += 1;
        Some(sample)
    }

    /// Resets the decoder so that decoding starts from the beginning of the file.
    pub fn reset(&mut self) {
        *self = QoaDecoder::new(self.data).expect("Failed to reset QOA decoder");
    }

    /// Loads the next frame by parsing its header and mono LMS state.
    ///
    /// The frame header is 8 bytes:
    ///   - 1 byte: number of channels (must be 1)
    ///   - 3 bytes: samplerate (24-bit big-endian)
    ///   - 2 bytes: fsamples (samples per channel in this frame)
    ///   - 2 bytes: fsize (frame size, including header)
    ///
    /// Followed by 16 bytes of LMS state (8 bytes history, 8 bytes weights).
    fn load_next_frame(&mut self) -> Result<()> {
        if self.pos + 8 > self.data.len() {
            return Err(QoaError::UnexpectedEof);
        }
        let num_channels = self.data[self.pos];
        if num_channels != 1 {
            panic!("Multiple channels not supported");
        }
        let samplerate = ((self.data[self.pos + 1] as u32) << 16)
            | ((self.data[self.pos + 2] as u32) << 8)
            | (self.data[self.pos + 3] as u32);
        if self.samples_read == 0 {
            self.sample_rate = samplerate;
        } else if self.sample_rate != samplerate {
            panic!("Samplerate changed across frames in non-streaming file");
        }
        let fsamples = u16::from_be_bytes(self.data[self.pos + 4..self.pos + 6].try_into().unwrap());
        let _fsize = u16::from_be_bytes(self.data[self.pos + 6..self.pos + 8].try_into().unwrap());
        self.pos += 8;
        if self.pos + 16 > self.data.len() {
            return Err(QoaError::UnexpectedEof);
        }
        self.lms = Lms::from_bytes(&self.data[self.pos..self.pos + 16]);
        self.pos += 16;
        self.slices_in_frame = ((fsamples as u32) + 19) / 20;
        self.current_slice_index = 0;
        self.slice_buffer_index = 20; // Buffer is empty.
        self.slice_buffer_len = 0;
        self.frame_samples_remaining = fsamples as u32;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{QoaDecoder, QoaError};

    // 1. Valid QOA file with one frame and one slice (20 samples).
    // File header (8 bytes):
    //   - Magic: "qoaf" (0x71, 0x6F, 0x61, 0x66)
    //   - Total samples: 20 (0x00, 0x00, 0x00, 0x14)
    // Frame header (8 bytes):
    //   - num_channels: 1
    //   - samplerate: 44100 (0x00, 0xAC, 0x44)
    //   - fsamples: 20 (0x00, 0x14)
    //   - fsize: 32 (0x00, 0x20)
    // LMS state (16 bytes): all zeros.
    // One slice (8 bytes): all zeros.
    const VALID_QOA: [u8; 40] = [
        // File header:
        0x71, 0x6F, 0x61, 0x66, // "qoaf"
        0x00, 0x00, 0x00, 0x14, // total samples = 20
        // Frame header:
        0x01,                   // num_channels = 1
        0x00, 0xAC, 0x44,       // samplerate = 44100
        0x00, 0x14,             // fsamples = 20
        0x00, 0x20,             // fsize = 32
        // LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // One slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    // 2. Multi-frame file:
    // Total samples = 30.
    // First frame: fsamples = 20, fsize = 32.
    // Second frame: fsamples = 10, fsize = 32.
    // Both frames use the same samplerate and LMS state (all zeros) and one slice each.
    const MULTIFRAME_QOA: [u8; 72] = [
        // File header:
        0x71, 0x6F, 0x61, 0x66, // "qoaf"
        0x00, 0x00, 0x00, 0x1E, // total samples = 30 (0x1E)
        // First frame header:
        0x01,                   // num_channels = 1
        0x00, 0xAC, 0x44,       // samplerate = 44100
        0x00, 0x14,             // fsamples = 20
        0x00, 0x20,             // fsize = 32
        // First frame LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // First frame slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // Second frame header:
        0x01,                   // num_channels = 1
        0x00, 0xAC, 0x44,       // samplerate = 44100
        0x00, 0x0A,             // fsamples = 10
        0x00, 0x20,             // fsize = 32
        // Second frame LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // Second frame slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    // 3. File with an invalid magic header.
    const INVALID_MAGIC: [u8; 40] = [
        0x78, 0x6F, 0x61, 0x66, // "xoaf" (invalid magic)
        0x00, 0x00, 0x00, 0x14, // total samples = 20
        0x01, 0x00, 0xAC, 0x44, // frame header
        0x00, 0x14,
        0x00, 0x20,
        // LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // One slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    // 4. File with a truncated file header (less than 8 bytes).
    const TRUNCATED_HEADER: [u8; 4] = [0x71, 0x6F, 0x61, 0x66];

    // 5. File with a truncated frame header (file header OK, but frame header incomplete).
    const TRUNCATED_FRAME_HEADER: [u8; 10] = [
        0x71, 0x6F, 0x61, 0x66, // "qoaf"
        0x00, 0x00, 0x00, 0x14, // total samples = 20
        0x01, 0x00, // incomplete frame header (only 2 bytes, expected 8)
    ];

    // 6. File with truncated LMS state (LMS state not complete).
    // File header + complete frame header + only 8 bytes of LMS state (instead of 16).
    const TRUNCATED_LMS: [u8; 8 + 8 + 8] = [
        0x71, 0x6F, 0x61, 0x66, // file header magic
        0x00, 0x00, 0x00, 0x14, // total samples = 20
        // Frame header (8 bytes):
        0x01, 0x00, 0xAC, 0x44, 0x00, 0x14, 0x00, 0x20,
        // LMS state (only 8 bytes, should be 16):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    // 7. File with multiple channels (num_channels != 1). Expect a panic.
    const MULTIPLE_CHANNELS: [u8; 40] = [
        0x71, 0x6F, 0x61, 0x66,
        0x00, 0x00, 0x00, 0x14,
        0x02,                   // num_channels = 2 (should panic)
        0x00, 0xAC, 0x44,
        0x00, 0x14,
        0x00, 0x20,
        // LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // One slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    // 8. File with a samplerate change between frames.
    // First frame: samplerate = 44100.
    // Second frame: samplerate changes to 48000.
    // This should cause a panic when decoding the second frame.
    const SAMPLERATE_CHANGE: [u8; 72] = [
        // File header:
        0x71, 0x6F, 0x61, 0x66,
        0x00, 0x00, 0x00, 0x1E, // total samples = 30
        // First frame header:
        0x01,                   // num_channels = 1
        0x00, 0xAC, 0x44,       // samplerate = 44100
        0x00, 0x14,             // fsamples = 20
        0x00, 0x20,             // fsize = 32
        // First frame LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // First frame slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // Second frame header:
        0x01,                   // num_channels = 1
        0x00, 0xBB, 0x80,       // samplerate = 48000 (changed)
        0x00, 0x0A,             // fsamples = 10
        0x00, 0x20,             // fsize = 32
        // Second frame LMS state (16 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        // Second frame slice (8 bytes):
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ];

    #[test]
    fn test_valid_qoa_decoding() {
        let mut decoder = QoaDecoder::new(&VALID_QOA).expect("Decoder creation failed");
        // We expect exactly 20 samples, each decodes to 1.
        for _ in 0..20 {
            assert_eq!(decoder.next_sample(), Some(1));
        }
        // After reading all samples, no more samples should be available.
        assert_eq!(decoder.next_sample(), None);
    }

    #[test]
    fn test_reset() {
        let mut decoder = QoaDecoder::new(&VALID_QOA).expect("Decoder creation failed");
        // Consume a few samples.
        for _ in 0..5 {
            assert_eq!(decoder.next_sample(), Some(1));
        }
        // Reset the decoder; output should restart.
        decoder.reset();
        for _ in 0..20 {
            assert_eq!(decoder.next_sample(), Some(1));
        }
        assert_eq!(decoder.next_sample(), None);
    }

    #[test]
    fn test_multiframe_decoding() {
        let mut decoder = QoaDecoder::new(&MULTIFRAME_QOA).expect("Decoder creation failed");
        // Total samples = 30 (20 from first frame, 10 from second).
        for _ in 0..30 {
            assert_eq!(decoder.next_sample(), Some(1));
        }
        assert_eq!(decoder.next_sample(), None);
    }

    #[test]
    fn test_invalid_magic() {
        match QoaDecoder::new(&INVALID_MAGIC) {
            Err(QoaError::InvalidFormat(_)) => { }
            _ => panic!("Expected InvalidFormat error due to invalid magic header"),
        }
    }

    #[test]
    fn test_truncated_header() {
        match QoaDecoder::new(&TRUNCATED_HEADER) {
            Err(QoaError::UnexpectedEof) => { }
            _ => panic!("Expected UnexpectedEof error due to truncated header"),
        }
    }

    #[test]
    fn test_truncated_frame_header() {
        match QoaDecoder::new(&TRUNCATED_FRAME_HEADER) {
            Err(QoaError::UnexpectedEof) => { }
            _ => panic!("Expected UnexpectedEof error due to truncated frame header"),
        }
    }

    #[test]
    fn test_truncated_lms_state() {
        match QoaDecoder::new(&TRUNCATED_LMS) {
            Err(QoaError::UnexpectedEof) => { }
            _ => panic!("Expected UnexpectedEof error due to truncated LMS state"),
        }
    }

    #[test]
    #[should_panic(expected = "Multiple channels not supported")]
    fn test_multiple_channels() {
        let _ = QoaDecoder::new(&MULTIPLE_CHANNELS);
    }

    #[test]
    #[should_panic(expected = "Samplerate changed across frames")]
    fn test_samplerate_change() {
        let _ = QoaDecoder::new(&SAMPLERATE_CHANGE).unwrap();
    }
}
