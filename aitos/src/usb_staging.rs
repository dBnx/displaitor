//! Packet retention between asynchronous CDC I/O and the stop-and-wait protocol.
//!
//! A USB packet can contain the tail of one request and the start of another.
//! Retain that suffix until the preceding reply has actually been transmitted.
use displaitor::{canvas::Canvas, canvas_protocol::Endpoint};

pub const PACKET_BYTES: usize = 64;

pub struct UsbStaging {
    endpoint: Endpoint,
    bytes: [u8; PACKET_BYTES],
    start: usize,
    end: usize,
}

impl Default for UsbStaging {
    fn default() -> Self {
        Self::new()
    }
}

impl UsbStaging {
    pub const fn new() -> Self {
        Self {
            endpoint: Endpoint::new(),
            bytes: [0; PACKET_BYTES],
            start: 0,
            end: 0,
        }
    }

    pub fn reset(&mut self, canvas: &mut Canvas) {
        self.endpoint.reset(canvas);
        self.start = 0;
        self.end = 0;
    }

    pub fn buffered(&self) -> bool {
        self.start != self.end
    }

    /// Returns false instead of replacing an unread packet or pending reply.
    pub fn push(&mut self, bytes: &[u8]) -> bool {
        if self.buffered() || !self.pending().is_empty() || bytes.len() > PACKET_BYTES {
            return false;
        }
        self.bytes[..bytes.len()].copy_from_slice(bytes);
        self.start = 0;
        self.end = bytes.len();
        true
    }

    /// Performs at most one USB packet of work, stopping at the first reply.
    pub fn drain(&mut self, canvas: &mut Canvas) -> bool {
        while self.buffered() && self.endpoint.pending().is_empty() {
            self.endpoint.receive(self.bytes[self.start], canvas);
            self.start += 1;
        }
        self.endpoint.take_show_request()
    }

    pub fn pending(&self) -> &[u8] {
        self.endpoint.pending()
    }

    pub fn written(&mut self, count: usize) {
        self.endpoint.written(count);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use displaitor::canvas_protocol::{crc32, encode};

    fn request(command: u8, sequence: u16) -> ([u8; 16], usize) {
        let [low, high] = sequence.to_le_bytes();
        let mut packet = [1, command, low, high, 0, 0, 0, 0];
        let crc = crc32(&packet[..4]);
        packet[4..].copy_from_slice(&crc.to_le_bytes());
        let mut encoded = [0; 16];
        let len = encode(&packet, &mut encoded).unwrap();
        (encoded, len)
    }

    #[test]
    fn reply_backpressure_preserves_the_next_request_suffix() {
        let mut staging = UsbStaging::new();
        let mut canvas = Canvas::new();
        let (first, first_len) = request(0, 1);
        let (second, second_len) = request(6, 2);
        let mut packet = [0; PACKET_BYTES];
        packet[..first_len].copy_from_slice(&first[..first_len]);
        packet[first_len..first_len + second_len].copy_from_slice(&second[..second_len]);
        assert!(staging.push(&packet[..first_len + second_len]));
        assert!(!staging.drain(&mut canvas));
        let reply = staging.pending().to_vec();
        assert!(staging.buffered());
        assert!(!staging.push(&first[..first_len]));
        assert!(!staging.drain(&mut canvas));
        assert_eq!(staging.pending(), reply);
        // Repeated polls and cancellation do not acknowledge a partial write.
        staging.written(5);
        assert_eq!(staging.pending(), &reply[5..]);
        assert!(!staging.drain(&mut canvas));
        staging.written(usize::MAX);
        assert!(staging.drain(&mut canvas));
        assert!(!staging.buffered());
        assert!(!staging.pending().is_empty());
    }

    #[test]
    fn split_requests_survive_idle_and_canceled_service_calls() {
        let mut staging = UsbStaging::new();
        let mut canvas = Canvas::new();
        let (packet, len) = request(6, 42);
        assert!(staging.push(&packet[..3]));
        assert!(!staging.drain(&mut canvas));
        assert!(staging.pending().is_empty());
        assert!(!staging.drain(&mut canvas));
        assert!(staging.push(&packet[3..len]));
        assert!(staging.drain(&mut canvas));
        assert!(!staging.pending().is_empty());
    }

    #[test]
    fn session_reset_discards_suffix_reply_and_uncommitted_scene() {
        let mut staging = UsbStaging::new();
        let mut canvas = Canvas::new();
        let (begin, len) = request(7, 1);
        let (show, show_len) = request(6, 2);
        let mut packet = [0; PACKET_BYTES];
        packet[..len].copy_from_slice(&begin[..len]);
        packet[len..len + show_len].copy_from_slice(&show[..show_len]);
        assert!(staging.push(&packet[..len + show_len]));
        assert!(!staging.drain(&mut canvas));
        staging.reset(&mut canvas);
        assert!(staging.pending().is_empty());
        assert!(!staging.buffered());
        assert!(!staging.drain(&mut canvas));
        // Commit is rejected: reset also aborted the Canvas transaction.
        assert!(canvas.apply(8, &[]).is_err());
        assert!(staging.push(&show[..show_len]));
        assert!(staging.drain(&mut canvas));
    }

    #[test]
    fn reset_discards_partial_protocol_envelopes() {
        let mut staging = UsbStaging::new();
        let mut canvas = Canvas::new();
        let (packet, len) = request(6, 42);
        assert!(staging.push(&packet[..3]));
        assert!(!staging.drain(&mut canvas));
        staging.reset(&mut canvas);
        assert!(staging.push(&packet[3..len]));
        assert!(!staging.drain(&mut canvas));
        assert!(staging.pending().is_empty());
        assert!(staging.push(&packet[..len]));
        assert!(staging.drain(&mut canvas));
    }
}
