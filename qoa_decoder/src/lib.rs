#![no_std]
#![forbid(unsafe_code)]

#[cfg(test)]
extern crate std;

mod lms;

use core::convert::TryInto;

use lms::Lms;

const FILE_HEADER_SIZE: usize = 8;
const FRAME_HEADER_SIZE: usize = 8;
const LMS_STATE_SIZE: usize = 16;
const SLICE_SIZE: usize = 8;
const SLICE_SAMPLES: u32 = 20;
const SLICES_PER_FRAME: u32 = 256;
const SAMPLES_PER_FRAME: u32 = SLICE_SAMPLES * SLICES_PER_FRAME;

/// Errors found while reading a QOA file.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum QoaError {
    /// The file header does not begin with `qoaf`.
    InvalidMagic,
    /// QOA files must declare at least one sample.
    EmptyFile,
    /// The mono sample iterator cannot decode this channel count.
    UnsupportedChannels(u8),
    /// QOA sample rates must be in 1..=0x00ff_ffff.
    InvalidSampleRate,
    /// A frame header or declared frame size violates the QOA format.
    InvalidFrame,
    /// The input ends before all declared frames and slices are present.
    UnexpectedEof,
    /// The frames do not contain the sample count declared by the file header.
    SampleCountMismatch,
    /// Bytes remain after the final declared frame.
    TrailingData,
}

pub type Result<T> = core::result::Result<T, QoaError>;

/// Decoder for static, mono QOA files.
///
/// Samples are decoded incrementally into a fixed 20-sample buffer. No heap
/// allocation is used. Stereo and multichannel files are rejected by `new`;
/// use a channel-aware decoder for those files.
pub struct QoaDecoder<'a> {
    data: &'a [u8],
    pos: usize,
    total_samples: u32,
    samples_left: u32,
    sample_rate: u32,
    frame_samples_left: u32,
    slices_left: u16,
    slice: [i16; SLICE_SAMPLES as usize],
    slice_pos: usize,
    slice_len: usize,
    lms: Lms,
}

impl<'a> QoaDecoder<'a> {
    /// Creates a decoder after validating the complete file structure.
    pub fn new(data: &'a [u8]) -> Result<Self> {
        let (total_samples, sample_rate) = validate_file(data)?;
        let mut decoder = Self {
            data,
            pos: FILE_HEADER_SIZE,
            total_samples,
            samples_left: total_samples,
            sample_rate,
            frame_samples_left: 0,
            slices_left: 0,
            slice: [0; SLICE_SAMPLES as usize],
            slice_pos: SLICE_SAMPLES as usize,
            slice_len: 0,
            lms: Lms::new(),
        };
        decoder.load_frame()?;
        Ok(decoder)
    }

    /// Returns the sample rate in hertz.
    pub const fn sample_rate(&self) -> u32 {
        self.sample_rate
    }

    /// Returns the next sample, or `None` after the declared samples are read.
    ///
    /// This compatibility method suppresses format errors as EOF. New callers
    /// should use [`try_next_sample`](Self::try_next_sample).
    pub fn next_sample(&mut self) -> Option<i16> {
        self.try_next_sample().ok().flatten()
    }

    /// Returns the next sample, preserving malformed-input errors.
    pub fn try_next_sample(&mut self) -> Result<Option<i16>> {
        if self.samples_left == 0 {
            return Ok(None);
        }

        if self.slice_pos >= self.slice_len {
            if self.slices_left == 0 {
                self.load_frame()?;
            }
            self.decode_slice()?;
        }

        let sample = self.slice[self.slice_pos];
        self.slice_pos += 1;
        self.samples_left -= 1;
        Ok(Some(sample))
    }

    /// Restarts decoding from the beginning of the already validated file.
    pub fn reset(&mut self) {
        self.pos = FILE_HEADER_SIZE;
        self.samples_left = self.total_samples;
        self.frame_samples_left = 0;
        self.slices_left = 0;
        self.slice = [0; SLICE_SAMPLES as usize];
        self.slice_pos = SLICE_SAMPLES as usize;
        self.slice_len = 0;
        self.lms = Lms::new();
        // The input was fully validated in `new`, so this cannot fail unless
        // the decoder's internal invariants are changed.
        let _ = self.load_frame();
    }

    fn load_frame(&mut self) -> Result<()> {
        let header_end = self
            .pos
            .checked_add(FRAME_HEADER_SIZE)
            .ok_or(QoaError::UnexpectedEof)?;
        let header = self
            .data
            .get(self.pos..header_end)
            .ok_or(QoaError::UnexpectedEof)?;
        let channels = header[0];
        if channels != 1 {
            return Err(QoaError::UnsupportedChannels(channels));
        }
        let samples = u16::from_be_bytes([header[4], header[5]]) as u32;
        let slices = samples.div_ceil(SLICE_SAMPLES);
        let frame_size = u16::from_be_bytes([header[6], header[7]]) as usize;
        self.pos = header_end;

        let state_end = self
            .pos
            .checked_add(LMS_STATE_SIZE)
            .ok_or(QoaError::UnexpectedEof)?;
        let state = self
            .data
            .get(self.pos..state_end)
            .ok_or(QoaError::UnexpectedEof)?;
        self.lms = Lms::from_bytes(state);
        self.pos = state_end;
        self.frame_samples_left = samples;
        self.slices_left = slices as u16;
        self.slice_pos = SLICE_SAMPLES as usize;
        self.slice_len = 0;

        let expected_size = FRAME_HEADER_SIZE + LMS_STATE_SIZE + slices as usize * SLICE_SIZE;
        if frame_size != expected_size {
            return Err(QoaError::InvalidFrame);
        }
        Ok(())
    }

    fn decode_slice(&mut self) -> Result<()> {
        if self.slices_left == 0 {
            return Err(QoaError::InvalidFrame);
        }
        let end = self
            .pos
            .checked_add(SLICE_SIZE)
            .ok_or(QoaError::UnexpectedEof)?;
        let bytes = self
            .data
            .get(self.pos..end)
            .ok_or(QoaError::UnexpectedEof)?;
        let bits = u64::from_be_bytes(bytes.try_into().map_err(|_| QoaError::UnexpectedEof)?);
        self.pos = end;
        self.slices_left -= 1;

        let scale_factor = (bits >> 60) as usize;
        let valid_samples = self.frame_samples_left.min(SLICE_SAMPLES) as usize;
        for index in 0..valid_samples {
            let shift = 57 - 3 * index;
            let quantized = ((bits >> shift) & 0x7) as usize;
            let residual = QOA_DEQUANT_TAB[scale_factor][quantized];
            let prediction = self.lms.predict();
            let sample =
                (prediction + residual as i64).clamp(i16::MIN as i64, i16::MAX as i64) as i16;
            self.slice[index] = sample;
            self.lms.update(sample, residual);
        }

        self.frame_samples_left -= valid_samples as u32;
        self.slice_pos = 0;
        self.slice_len = valid_samples;
        Ok(())
    }
}

fn validate_file(data: &[u8]) -> Result<(u32, u32)> {
    let file_header = data
        .get(..FILE_HEADER_SIZE)
        .ok_or(QoaError::UnexpectedEof)?;
    if &file_header[..4] != b"qoaf" {
        return Err(QoaError::InvalidMagic);
    }
    let total_samples = u32::from_be_bytes(
        file_header[4..8]
            .try_into()
            .map_err(|_| QoaError::UnexpectedEof)?,
    );
    if total_samples == 0 {
        return Err(QoaError::EmptyFile);
    }

    let mut pos = FILE_HEADER_SIZE;
    let mut samples_seen = 0u32;
    let mut sample_rate = None;
    while samples_seen < total_samples {
        let header_end = pos
            .checked_add(FRAME_HEADER_SIZE)
            .ok_or(QoaError::UnexpectedEof)?;
        let header = data.get(pos..header_end).ok_or(QoaError::UnexpectedEof)?;
        let channels = header[0];
        if channels != 1 {
            return Err(QoaError::UnsupportedChannels(channels));
        }
        let frame_rate = ((header[1] as u32) << 16) | ((header[2] as u32) << 8) | header[3] as u32;
        if frame_rate == 0 {
            return Err(QoaError::InvalidSampleRate);
        }
        if sample_rate.is_some_and(|rate| rate != frame_rate) {
            return Err(QoaError::InvalidFrame);
        }
        sample_rate = Some(frame_rate);

        let frame_samples = u16::from_be_bytes([header[4], header[5]]) as u32;
        if frame_samples == 0 || frame_samples > SAMPLES_PER_FRAME {
            return Err(QoaError::InvalidFrame);
        }
        let remaining = total_samples - samples_seen;
        if frame_samples > remaining
            || (frame_samples < remaining && frame_samples != SAMPLES_PER_FRAME)
        {
            return Err(QoaError::SampleCountMismatch);
        }
        let slices = frame_samples.div_ceil(SLICE_SAMPLES);
        let expected_size = FRAME_HEADER_SIZE + LMS_STATE_SIZE + slices as usize * SLICE_SIZE;
        let frame_size = u16::from_be_bytes([header[6], header[7]]) as usize;
        if frame_size != expected_size {
            return Err(QoaError::InvalidFrame);
        }
        let frame_end = pos.checked_add(frame_size).ok_or(QoaError::UnexpectedEof)?;
        data.get(pos..frame_end).ok_or(QoaError::UnexpectedEof)?;
        pos = frame_end;
        samples_seen += frame_samples;
    }

    if pos != data.len() {
        return Err(QoaError::TrailingData);
    }
    Ok((
        total_samples,
        sample_rate.ok_or(QoaError::SampleCountMismatch)?,
    ))
}

/// QOA's dequantized residual values, indexed by scalefactor and 3-bit value.
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

#[cfg(test)]
mod tests {
    use super::{LMS_STATE_SIZE, QoaDecoder, QoaError, SAMPLES_PER_FRAME};

    fn mono_file(samples: u32, frame_samples: u16, slice: u64) -> std::vec::Vec<u8> {
        let slices = (frame_samples as usize).div_ceil(20);
        let frame_size = 24 + slices * 8;
        let mut bytes = std::vec::Vec::with_capacity(8 + frame_size);
        bytes.extend_from_slice(b"qoaf");
        bytes.extend_from_slice(&samples.to_be_bytes());
        bytes.extend_from_slice(&[1, 0x00, 0xac, 0x44]);
        bytes.extend_from_slice(&frame_samples.to_be_bytes());
        bytes.extend_from_slice(&(frame_size as u16).to_be_bytes());
        bytes.extend_from_slice(&[0; 16]);
        for _ in 0..slices {
            bytes.extend_from_slice(&slice.to_be_bytes());
        }
        bytes
    }

    #[test]
    fn decodes_reference_zero_lms_slice_and_resets() {
        // Generated with phoboslab/qoa's qoa_encode_frame/qoa_decode_frame;
        // zero LMS and a zero slice decode as twenty scale-zero residuals of +1.
        let bytes = mono_file(20, 20, 0);
        let mut decoder = QoaDecoder::new(&bytes).unwrap();
        assert_eq!(decoder.sample_rate(), 44_100);
        let samples: std::vec::Vec<_> =
            core::iter::from_fn(|| decoder.try_next_sample().unwrap()).collect();
        assert_eq!(samples, [1; 20]);
        assert_eq!(decoder.try_next_sample(), Ok(None));
        decoder.reset();
        assert_eq!(decoder.try_next_sample(), Ok(Some(1)));
    }

    #[test]
    fn matches_phoboslab_reference_decoder_samples() {
        let mut packed = 0u64;
        for index in 0..20 {
            packed = (packed << 3) | (index % 8) as u64;
        }
        // Samples independently printed by phoboslab/qoa's qoa_decode for
        // this exact zero-LMS, scale-zero slice.
        let expected = [
            1, -1, 3, -4, 5, -6, 7, -8, 1, -2, 3, -4, 5, -6, 7, -8, 1, -2, 3, -4,
        ];
        let bytes = mono_file(20, 20, packed);
        let mut decoder = QoaDecoder::new(&bytes).unwrap();
        for sample in expected {
            assert_eq!(decoder.try_next_sample(), Ok(Some(sample)));
        }
        assert_eq!(decoder.try_next_sample(), Ok(None));
    }

    #[test]
    fn reports_partial_final_slice_and_eof_exactly() {
        let bytes = mono_file(3, 3, 0);
        let mut decoder = QoaDecoder::new(&bytes).unwrap();
        assert_eq!(decoder.try_next_sample(), Ok(Some(1)));
        assert_eq!(decoder.try_next_sample(), Ok(Some(1)));
        assert_eq!(decoder.try_next_sample(), Ok(Some(1)));
        assert_eq!(decoder.try_next_sample(), Ok(None));
    }

    #[test]
    fn rejects_stereo_and_malformed_boundaries() {
        let mut stereo = mono_file(20, 20, 0);
        stereo[8] = 2;
        assert!(matches!(
            QoaDecoder::new(&stereo),
            Err(QoaError::UnsupportedChannels(2))
        ));

        let valid = mono_file(20, 20, 0);
        assert!(matches!(
            QoaDecoder::new(&valid[..7]),
            Err(QoaError::UnexpectedEof)
        ));
        assert!(matches!(
            QoaDecoder::new(&valid[..valid.len() - 1]),
            Err(QoaError::UnexpectedEof)
        ));

        let mut bad_frame_size = valid.clone();
        bad_frame_size[14] = 0;
        bad_frame_size[15] = 31;
        assert!(matches!(
            QoaDecoder::new(&bad_frame_size),
            Err(QoaError::InvalidFrame)
        ));

        let mut bad_count = valid.clone();
        bad_count[7] = 21;
        assert!(matches!(
            QoaDecoder::new(&bad_count),
            Err(QoaError::SampleCountMismatch)
        ));

        let mut trailing = valid;
        trailing.push(0);
        assert!(matches!(
            QoaDecoder::new(&trailing),
            Err(QoaError::TrailingData)
        ));
    }

    #[test]
    fn rejects_every_truncated_prefix_without_panicking() {
        let valid = mono_file(20, 20, 0);
        for end in 0..valid.len() {
            let result = std::panic::catch_unwind(|| QoaDecoder::new(&valid[..end]));
            assert!(
                result.is_ok(),
                "constructor panicked for prefix length {end}"
            );
            assert!(result.unwrap().is_err(), "accepted prefix length {end}");
        }
    }

    #[test]
    fn rejects_invalid_rate_zero_and_rate_changes() {
        let valid = mono_file(20, 20, 0);
        let mut zero_rate = valid.clone();
        zero_rate[9..12].fill(0);
        assert!(matches!(
            QoaDecoder::new(&zero_rate),
            Err(QoaError::InvalidSampleRate)
        ));

        let mut two_frames = mono_file(SAMPLES_PER_FRAME + 1, SAMPLES_PER_FRAME as u16, 0);
        two_frames.extend_from_slice(&[
            1, 0x00, 0xac, 0x45, // changed sample rate
            0, 1, // one sample
            0, 32, // 24-byte header/state + one slice
        ]);
        two_frames.extend_from_slice(&[0; LMS_STATE_SIZE]);
        two_frames.extend_from_slice(&0u64.to_be_bytes());
        assert!(matches!(
            QoaDecoder::new(&two_frames),
            Err(QoaError::InvalidFrame)
        ));
    }

    #[test]
    fn extreme_lms_state_decodes_without_integer_overflow() {
        let mut bytes = mono_file(20, 20, u64::MAX);
        for pair in bytes[16..24].as_chunks_mut::<2>().0 {
            pair.copy_from_slice(&i16::MIN.to_be_bytes());
        }
        for pair in bytes[24..32].as_chunks_mut::<2>().0 {
            pair.copy_from_slice(&i16::MAX.to_be_bytes());
        }

        let result = std::panic::catch_unwind(|| {
            let mut decoder = QoaDecoder::new(&bytes).unwrap();
            let mut count = 0;
            while decoder.try_next_sample().unwrap().is_some() {
                count += 1;
            }
            count
        });
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 20);
    }
}
