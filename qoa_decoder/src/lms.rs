/// The per-channel QOA least-mean-squares predictor state.
pub struct Lms {
    history: [i16; 4],
    weights: [i32; 4],
}

impl Lms {
    pub const fn new() -> Self {
        Self {
            history: [0; 4],
            weights: [0; 4],
        }
    }

    /// Reads the 4 signed history samples and 4 signed weights from a frame.
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let mut history = [0; 4];
        let mut weights = [0; 4];
        for i in 0..4 {
            let offset = i * 2;
            history[i] = i16::from_be_bytes([bytes[offset], bytes[offset + 1]]);
            let weight_offset = 8 + offset;
            weights[i] =
                i16::from_be_bytes([bytes[weight_offset], bytes[weight_offset + 1]]) as i32;
        }
        Self { history, weights }
    }

    pub fn predict(&self) -> i64 {
        let mut prediction = 0i64;
        for i in 0..4 {
            prediction += self.weights[i] as i64 * self.history[i] as i64;
        }
        prediction >> 13
    }

    pub fn update(&mut self, sample: i16, residual: i32) {
        let delta = residual >> 4;
        for i in 0..4 {
            self.weights[i] += if self.history[i] < 0 { -delta } else { delta };
        }
        self.history.copy_within(1..4, 0);
        self.history[3] = sample;
    }
}
