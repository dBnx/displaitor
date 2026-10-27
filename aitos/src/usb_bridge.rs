//! Actual foreground USB bridge shared by firmware and directed host tests.
//!
//! Only owned packets cross executor boundaries. Every channel has one slot;
//! protocol replies and packet suffixes survive cancellation and backpressure.
use crate::usb_staging::{PACKET_BYTES, UsbStaging};
use core::cell::Cell;
use displaitor::{Engine, canvas_protocol::MAX_REPLY};
use embassy_futures::select::{Either, select};
use embassy_sync::{
    blocking_mutex::{Mutex, raw::CriticalSectionRawMutex},
    channel::Channel,
    signal::Signal,
};

#[derive(Clone, Copy)]
pub struct Session {
    pub generation: u32,
    pub open: bool,
}
#[derive(Clone, Copy)]
pub struct Packet {
    pub generation: u32,
    pub bytes: [u8; PACKET_BYTES],
    pub len: usize,
}
#[derive(Clone, Copy)]
pub struct Reply {
    pub generation: u32,
    pub bytes: [u8; MAX_REPLY],
    pub len: usize,
}
#[derive(Clone, Copy)]
pub struct Written {
    pub generation: u32,
    pub len: usize,
}

/// Private-to-the-adapter transport boundary, independently instantiable in tests.
pub struct Bridge {
    session: Mutex<CriticalSectionRawMutex, Cell<Session>>,
    session_changed: Signal<CriticalSectionRawMutex, ()>,
    pub incoming: Channel<CriticalSectionRawMutex, Packet, 1>,
    pub outgoing: Channel<CriticalSectionRawMutex, Reply, 1>,
    pub written: Channel<CriticalSectionRawMutex, Written, 1>,
}
impl Bridge {
    pub const fn new() -> Self {
        Self {
            session: Mutex::new(Cell::new(Session {
                generation: 0,
                open: false,
            })),
            session_changed: Signal::new(),
            incoming: Channel::new(),
            outgoing: Channel::new(),
            written: Channel::new(),
        }
    }
    pub fn session(&self) -> Session {
        self.session.lock(Cell::get)
    }
    /// A full ingress queue must still allow the response that unblocks the UI.
    /// The caller retains its packet until the send branch completes.
    pub async fn forward_incoming(&self, packet: Packet) -> Either<Reply, ()> {
        select(self.outgoing.receive(), self.incoming.send(packet)).await
    }
    pub fn new_session(&self, open: bool) {
        self.session.lock(|value| {
            let old = value.get();
            value.set(Session {
                generation: old.generation.wrapping_add(1),
                open,
            });
        });
        // Lifecycle wakeup must remain independent of all channel backpressure.
        self.session_changed.signal(());
    }
}
impl Default for Bridge {
    fn default() -> Self {
        Self::new()
    }
}

pub static BRIDGE: Bridge = Bridge::new();

pub struct UsbCanvas<'a> {
    bridge: &'a Bridge,
    staging: UsbStaging,
    generation: u32,
    awaiting_write: bool,
}

impl UsbCanvas<'static> {
    pub fn new() -> Self {
        Self::with_bridge(&BRIDGE)
    }
}

impl Default for UsbCanvas<'static> {
    fn default() -> Self {
        Self::new()
    }
}

impl<'a> UsbCanvas<'a> {
    pub fn with_bridge(bridge: &'a Bridge) -> Self {
        Self {
            bridge,
            staging: UsbStaging::new(),
            generation: bridge.session().generation,
            awaiting_write: false,
        }
    }

    fn synchronize<const N: usize>(&mut self, engine: &mut Engine<N>) -> Session {
        let current = self.bridge.session();
        if current.generation != self.generation {
            self.staging.reset(engine.canvas_mut());
            self.awaiting_write = false;
            self.generation = current.generation;
        }
        current
    }

    /// One bounded operation, safe to cancel for input, rendering or deadlines.
    /// Nothing is removed from the protocol until its owned copy is transferred.
    pub async fn service<const N: usize>(&mut self, engine: &mut Engine<N>) {
        let current = self.synchronize(engine);
        if !current.open {
            self.bridge.session_changed.wait().await;
            self.synchronize(engine);
            return;
        }
        if self.awaiting_write {
            match select(
                self.bridge.session_changed.wait(),
                self.bridge.written.receive(),
            )
            .await
            {
                Either::First(()) => {
                    self.synchronize(engine);
                }
                Either::Second(ack) => {
                    let current = self.synchronize(engine);
                    if current.open && ack.generation == self.generation {
                        self.staging.written(ack.len);
                        self.awaiting_write = false;
                    }
                }
            }
            return;
        }
        if !self.staging.pending().is_empty() {
            let mut bytes = [0; MAX_REPLY];
            let len = self.staging.pending().len();
            bytes[..len].copy_from_slice(self.staging.pending());
            let reply = Reply {
                generation: self.generation,
                bytes,
                len,
            };
            match select(
                self.bridge.session_changed.wait(),
                self.bridge.outgoing.send(reply),
            )
            .await
            {
                Either::First(()) => {
                    self.synchronize(engine);
                }
                Either::Second(()) => self.awaiting_write = true,
            }
            return;
        }
        if self.staging.buffered() {
            if self.staging.drain(engine.canvas_mut()) {
                engine.request_canvas();
            }
            return;
        }
        match select(
            self.bridge.session_changed.wait(),
            self.bridge.incoming.receive(),
        )
        .await
        {
            Either::First(()) => {
                self.synchronize(engine);
            }
            Either::Second(packet) => {
                let current = self.synchronize(engine);
                if current.open && packet.generation == self.generation {
                    self.staging.push(&packet.bytes[..packet.len]);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    extern crate std;
    use super::*;
    use core::{
        future::Future,
        pin::Pin,
        sync::atomic::{AtomicUsize, Ordering},
        task::{Context, Poll, Waker},
    };
    use displaitor::canvas_protocol::{crc32, encode};
    use std::{boxed::Box, sync::Arc, task::Wake};

    #[derive(Default)]
    struct WakeCount(AtomicUsize);
    impl Wake for WakeCount {
        fn wake(self: Arc<Self>) {
            self.0.fetch_add(1, Ordering::Relaxed);
        }
        fn wake_by_ref(self: &Arc<Self>) {
            self.0.fetch_add(1, Ordering::Relaxed);
        }
    }
    fn poll<F: Future>(future: Pin<&mut F>, waker: &Waker) -> Poll<F::Output> {
        future.poll(&mut Context::from_waker(waker))
    }
    // Polling a fresh future exercises the same cancellation that the board's
    // select performs when input, presentation or a deadline wins the race.
    fn step(ui: &mut UsbCanvas<'_>, engine: &mut Engine, waker: &Waker) -> Poll<()> {
        let mut future = core::pin::pin!(ui.service(engine));
        poll(future.as_mut(), waker)
    }
    fn fixture<'a>(bridge: &'a Bridge, waker: &Waker) -> (UsbCanvas<'a>, Engine) {
        bridge.new_session(true);
        let mut ui = UsbCanvas::with_bridge(bridge);
        let mut engine = Engine::new();
        assert!(step(&mut ui, &mut engine, waker).is_ready());
        (ui, engine)
    }
    fn packet(generation: u32, command: u8, sequence: u16) -> Packet {
        let [low, high] = sequence.to_le_bytes();
        let mut request = [1, command, low, high, 0, 0, 0, 0];
        let crc = crc32(&request[..4]);
        request[4..].copy_from_slice(&crc.to_le_bytes());
        let mut bytes = [0; PACKET_BYTES];
        let len = encode(&request, &mut bytes).unwrap();
        Packet {
            generation,
            bytes,
            len,
        }
    }
    fn prepare_reply(
        bridge: &Bridge,
        ui: &mut UsbCanvas<'_>,
        engine: &mut Engine,
        command: u8,
        waker: &Waker,
    ) {
        assert!(
            bridge
                .incoming
                .try_send(packet(bridge.session().generation, command, 1))
                .is_ok()
        );
        assert!(step(ui, engine, waker).is_ready()); // Own the packet.
        assert!(step(ui, engine, waker).is_ready()); // Parse until its reply.
        assert!(!ui.staging.pending().is_empty());
    }
    fn dummy_reply(generation: u32) -> Reply {
        Reply {
            generation,
            bytes: [0; MAX_REPLY],
            len: 0,
        }
    }

    #[test]
    fn full_ingress_still_forwards_the_reply_needed_by_the_ui() {
        let bridge = Bridge::new();
        let count = Arc::new(WakeCount::default());
        let waker = Waker::from(count.clone());
        let queued = packet(1, 0, 1);
        let retained = packet(1, 0, 2);
        assert!(bridge.incoming.try_send(queued).is_ok());
        let mut forward = Box::pin(bridge.forward_incoming(retained));
        assert!(poll(forward.as_mut(), &waker).is_pending());
        drop(forward); // A lifecycle/deadline cancellation retains both packets.
        let mut forward = Box::pin(bridge.forward_incoming(retained));
        assert!(poll(forward.as_mut(), &waker).is_pending());
        assert!(bridge.outgoing.try_send(dummy_reply(1)).is_ok());
        assert!(count.0.load(Ordering::Relaxed) > 0);
        assert!(matches!(
            poll(forward.as_mut(), &waker),
            Poll::Ready(Either::First(_))
        ));
        drop(forward);
        // The original queued RX packet is untouched; the caller still owns the
        // second packet after the reply branch or a canceled forwarding future.
        assert_eq!(bridge.incoming.try_receive().unwrap().bytes, queued.bytes);
        let mut forward = Box::pin(bridge.forward_incoming(retained));
        assert!(matches!(
            poll(forward.as_mut(), &waker),
            Poll::Ready(Either::Second(()))
        ));
        drop(forward);
        assert_eq!(bridge.incoming.try_receive().unwrap().bytes, retained.bytes);
    }

    #[test]
    fn canceled_sends_and_ack_waits_retain_one_reply_without_duplicate_enqueues() {
        let bridge = Bridge::new();
        let waker = Waker::from(Arc::new(WakeCount::default()));
        let (mut ui, mut engine) = fixture(&bridge, &waker);
        prepare_reply(&bridge, &mut ui, &mut engine, 0, &waker);
        let expected = ui.staging.pending().to_vec();
        let generation = bridge.session().generation;
        assert!(bridge.outgoing.try_send(dummy_reply(generation)).is_ok());
        for _ in 0..3 {
            assert!(step(&mut ui, &mut engine, &waker).is_pending());
        }
        assert_eq!(ui.staging.pending(), expected);
        assert!(!ui.awaiting_write);
        bridge.outgoing.try_receive().unwrap();
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        let reply = bridge.outgoing.try_receive().unwrap();
        assert_eq!(&reply.bytes[..reply.len], expected);
        assert!(ui.awaiting_write);
        // Fill ingress while TX is blocked. This must neither consume RX nor
        // acknowledge or enqueue the current response a second time.
        assert!(bridge.incoming.try_send(packet(generation, 6, 2)).is_ok());
        for _ in 0..3 {
            assert!(step(&mut ui, &mut engine, &waker).is_pending());
        }
        assert!(bridge.incoming.is_full());
        assert!(bridge.outgoing.try_receive().is_err());
        assert_eq!(ui.staging.pending(), expected);
        assert!(
            bridge
                .written
                .try_send(Written {
                    generation,
                    len: reply.len
                })
                .is_ok()
        );
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        assert!(ui.staging.pending().is_empty());
        assert!(!ui.awaiting_write);
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        assert!(!bridge.incoming.is_full());
        assert!(!ui.staging.pending().is_empty());
    }

    #[test]
    fn reset_wakes_a_blocked_send_despite_full_queues_and_aborts_the_transaction() {
        let bridge = Bridge::new();
        let count = Arc::new(WakeCount::default());
        let waker = Waker::from(count.clone());
        let (mut ui, mut engine) = fixture(&bridge, &waker);
        prepare_reply(&bridge, &mut ui, &mut engine, 7, &waker); // Begin transaction.
        let generation = bridge.session().generation;
        assert!(bridge.outgoing.try_send(dummy_reply(generation)).is_ok());
        assert!(bridge.incoming.try_send(packet(generation, 8, 2)).is_ok());
        assert!(
            bridge
                .written
                .try_send(Written { generation, len: 1 })
                .is_ok()
        );
        let mut sending = Box::pin(ui.service(&mut engine));
        assert!(poll(sending.as_mut(), &waker).is_pending());
        let before = count.0.load(Ordering::Relaxed);
        bridge.new_session(false);
        assert!(count.0.load(Ordering::Relaxed) > before);
        assert!(poll(sending.as_mut(), &waker).is_ready());
        drop(sending);
        assert!(ui.staging.pending().is_empty());
        assert!(!ui.staging.buffered());
        assert!(!ui.awaiting_write);
        assert!(engine.canvas_mut().apply(8, &[]).is_err()); // Commit was aborted.
    }

    #[test]
    fn reopen_rejects_stale_rx_and_ack_without_advancing_the_new_reply() {
        let bridge = Bridge::new();
        let waker = Waker::from(Arc::new(WakeCount::default()));
        let (mut ui, mut engine) = fixture(&bridge, &waker);
        let old = bridge.session().generation;
        prepare_reply(&bridge, &mut ui, &mut engine, 7, &waker);
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        bridge.outgoing.try_receive().unwrap();
        let mut waiting = Box::pin(ui.service(&mut engine));
        assert!(poll(waiting.as_mut(), &waker).is_pending());
        assert!(bridge.incoming.try_send(packet(old, 7, 1)).is_ok());
        assert!(
            bridge
                .written
                .try_send(Written {
                    generation: old,
                    len: MAX_REPLY
                })
                .is_ok()
        );
        bridge.new_session(false);
        bridge.new_session(true); // Coalesced lifecycle wake, distinct generation.
        assert!(poll(waiting.as_mut(), &waker).is_ready());
        drop(waiting);
        assert!(!ui.awaiting_write);
        assert!(step(&mut ui, &mut engine, &waker).is_ready()); // Drop stale RX.
        assert!(!ui.staging.buffered());
        assert!(engine.canvas_mut().apply(8, &[]).is_err());
        prepare_reply(&bridge, &mut ui, &mut engine, 0, &waker);
        assert!(step(&mut ui, &mut engine, &waker).is_ready()); // Enqueue new reply.
        let reply = bridge.outgoing.try_receive().unwrap();
        let expected = ui.staging.pending().to_vec();
        assert!(step(&mut ui, &mut engine, &waker).is_ready()); // Drop stale ACK.
        assert!(ui.awaiting_write);
        assert_eq!(ui.staging.pending(), expected);
        assert!(step(&mut ui, &mut engine, &waker).is_pending());
        assert!(
            bridge
                .written
                .try_send(Written {
                    generation: reply.generation,
                    len: reply.len
                })
                .is_ok()
        );
        assert!(step(&mut ui, &mut engine, &waker).is_ready());
        assert!(!ui.awaiting_write);
        assert!(ui.staging.pending().is_empty());
    }
}
