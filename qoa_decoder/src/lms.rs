/// LMS state used for prediction and update.
/// Holds the 4-element history and 4-element weights.
pub struct Lms {
    pub history: [i16; 4],
    pub weights: [i16; 4],
}

impl Lms {
    pub fn new() -> Self {
        Lms {
            history: [0; 4],
            weights: [0; 4],
        }
    }

    /// Constructs an LMS state from a 16-byte big-endian slice.
    /// The first 8 bytes represent the history and the next 8 bytes the weights.
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let history = [
            i16::from_be_bytes(bytes[0..2].try_into().unwrap()),
            i16::from_be_bytes(bytes[2..4].try_into().unwrap()),
            i16::from_be_bytes(bytes[4..6].try_into().unwrap()),
            i16::from_be_bytes(bytes[6..8].try_into().unwrap()),
        ];
        let weights = [
            i16::from_be_bytes(bytes[8..10].try_into().unwrap()),
            i16::from_be_bytes(bytes[10..12].try_into().unwrap()),
            i16::from_be_bytes(bytes[12..14].try_into().unwrap()),
            i16::from_be_bytes(bytes[14..16].try_into().unwrap()),
        ];
        Lms { history, weights }
    }

    /// Computes the prediction: the weighted sum of the history, right-shifted by 13.
    /// Optimized: loop unrolled for better performance.
    #[inline(always)]
    pub fn predict(&self) -> i32 {
        // Unroll the loop for better performance - compiler can optimize better
        let p = (self.history[0] as i32 * self.weights[0] as i32)
            + (self.history[1] as i32 * self.weights[1] as i32)
            + (self.history[2] as i32 * self.weights[2] as i32)
            + (self.history[3] as i32 * self.weights[3] as i32);
        p >> 13
    }

    /// Updates the LMS state given the decoded sample `s` and the dequantized residual `r`.
    /// The update is performed in-place.
    /// Optimized: loop unrolled and history shift optimized.
    #[inline(always)]
    pub fn update(&mut self, s: i16, r: i32) {
        let delta = r >> 4;
        let delta_i16 = delta as i16;
        let neg_delta_i16 = (-delta) as i16;
        
        // Unroll loop - compiler can optimize better with branch prediction
        if self.history[0] < 0 {
            self.weights[0] = self.weights[0].wrapping_add(neg_delta_i16);
        } else {
            self.weights[0] = self.weights[0].wrapping_add(delta_i16);
        }
        if self.history[1] < 0 {
            self.weights[1] = self.weights[1].wrapping_add(neg_delta_i16);
        } else {
            self.weights[1] = self.weights[1].wrapping_add(delta_i16);
        }
        if self.history[2] < 0 {
            self.weights[2] = self.weights[2].wrapping_add(neg_delta_i16);
        } else {
            self.weights[2] = self.weights[2].wrapping_add(delta_i16);
        }
        if self.history[3] < 0 {
            self.weights[3] = self.weights[3].wrapping_add(neg_delta_i16);
        } else {
            self.weights[3] = self.weights[3].wrapping_add(delta_i16);
        }
        
        // Optimized history shift - manual rotation for better register usage
        self.history[0] = self.history[1];
        self.history[1] = self.history[2];
        self.history[2] = self.history[3];
        self.history[3] = s;
    }
}

#[cfg(test)]
mod tests {
    use super::Lms;

    #[test]
    fn test_new() {
        let lms = Lms::new();
        assert_eq!(lms.history, [0, 0, 0, 0]);
        assert_eq!(lms.weights, [0, 0, 0, 0]);
    }

    #[test]
    fn test_from_bytes() {
        // Prepare a 16-byte array where:
        // history: [1, 2, 3, 4] and weights: [5, 6, 7, 8], all as big-endian i16.
        let bytes: [u8; 16] = [
            0x00, 0x01, // 1
            0x00, 0x02, // 2
            0x00, 0x03, // 3
            0x00, 0x04, // 4
            0x00, 0x05, // 5
            0x00, 0x06, // 6
            0x00, 0x07, // 7
            0x00, 0x08, // 8
        ];
        let lms = Lms::from_bytes(&bytes);
        assert_eq!(lms.history, [1, 2, 3, 4]);
        assert_eq!(lms.weights, [5, 6, 7, 8]);
    }

    #[test]
    fn test_predict_zero() {
        let lms = Lms::new();
        // With all zeros, the prediction should be zero.
        assert_eq!(lms.predict(), 0);
    }

    #[test]
    fn test_predict_nonzero() {
        // Set up an LMS with a nonzero product:
        // Let history[0] = 8192 and weights[0] = 1, rest zero.
        // Then p = 8192, and 8192 >> 13 == 1 (since 8192/8192 == 1).
        let mut lms = Lms::new();
        lms.history = [8192, 0, 0, 0];
        lms.weights = [1, 0, 0, 0];
        assert_eq!(lms.predict(), 1);
    }

    #[test]
    fn test_update_positive() {
        // Start with an initial LMS state of zeros.
        let mut lms = Lms::new();
        // Let s = 100, r = 16.
        // Then delta = 16 >> 4 = 1.
        // For each element in history (which are 0 and thus not negative),
        // weights[i] get increased by 1.
        lms.update(100, 16);
        // After the update, weights should be [1, 1, 1, 1]
        // and history should be shifted: [0, 0, 0, 100].
        assert_eq!(lms.weights, [1, 1, 1, 1]);
        assert_eq!(lms.history, [0, 0, 0, 100]);
    }

    #[test]
    fn test_update_negative() {
        // Start with a nonzero state.
        // history: [-10, 5, 0, 20]
        // weights: [2, -3, 4, 0]
        let mut lms = Lms {
            history: [-10, 5, 0, 20],
            weights: [2, -3, 4, 0],
        };
        // Let s = -100, r = -32.
        // Then delta = -32 >> 4 = -2.
        // For each element:
        //   - index 0: history -10 (< 0) so weight[0] becomes 2 + (-(-2)) = 2 + 2 = 4.
        //   - index 1: history 5 (>= 0) so weight[1] becomes -3 + (-2) = -5.
        //   - index 2: history 0 (>= 0) so weight[2] becomes 4 + (-2) = 2.
        //   - index 3: history 20 (>= 0) so weight[3] becomes 0 + (-2) = -2.
        // Then, history becomes [5, 0, 20, -100].
        lms.update(-100, -32);
        assert_eq!(lms.weights, [4, -5, 2, -2]);
        assert_eq!(lms.history, [5, 0, 20, -100]);
    }

    #[test]
    fn test_update_chain() {
        // Chain multiple updates to verify cumulative behavior.
        let mut lms = Lms::new();
        // First update: s = 50, r = 32.
        // delta = 32 >> 4 = 2.
        lms.update(50, 32);
        // Expect weights: [2, 2, 2, 2] and history: [0, 0, 0, 50].
        assert_eq!(lms.weights, [2, 2, 2, 2]);
        assert_eq!(lms.history, [0, 0, 0, 50]);

        // Second update: s = 100, r = 64.
        // delta = 64 >> 4 = 4.
        // For each element in current history ([0, 0, 0, 50], all non-negative),
        // weights become each increased by 4: 2+4 = 6.
        // New history becomes [0, 0, 50, 100].
        lms.update(100, 64);
        assert_eq!(lms.weights, [6, 6, 6, 6]);
        assert_eq!(lms.history, [0, 0, 50, 100]);
    }
}
