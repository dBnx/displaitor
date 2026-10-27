//! Interrupt-executor USB transport and a cancellation-safe foreground adapter.
//!
//! CDC's internal control state is not Sync. Build and poll the device and all
//! class halves in the same task; only owned packets cross the executor boundary.
use core::{cell::Cell, future::Future, task::Poll};

pub use aitos::usb_bridge::UsbCanvas;
use aitos::{
    usb_bridge::{BRIDGE, Packet, Reply, Written},
    usb_staging::PACKET_BYTES,
};
use displaitor::canvas_protocol::MAX_REPLY;
use embassy_futures::{
    join::join,
    select::{Either, Either3, select, select3},
    yield_now,
};
use embassy_rp::{
    Peri,
    interrupt::typelevel::{Binding, USBCTRL_IRQ},
    peripherals::USB,
    usb::{Driver, InterruptHandler},
};
use embassy_sync::{
    blocking_mutex::{Mutex, raw::CriticalSectionRawMutex},
    signal::Signal,
};
use embassy_usb::{
    Builder, Config, Handler,
    class::cdc_acm::{CdcAcmClass, Receiver, State},
};

// Every reply ends in a short USB packet; no separate terminating ZLP is needed.
const _: () = assert!(MAX_REPLY < PACKET_BYTES);

static LIFECYCLE: Signal<CriticalSectionRawMutex, ()> = Signal::new();
static CONFIGURED: Mutex<CriticalSectionRawMutex, Cell<bool>> = Mutex::new(Cell::new(false));

struct Lifecycle;

impl Handler for Lifecycle {
    fn enabled(&mut self, enabled: bool) {
        if !enabled {
            CONFIGURED.lock(|value| value.set(false));
            LIFECYCLE.signal(());
        }
    }

    fn reset(&mut self) {
        CONFIGURED.lock(|value| value.set(false));
        LIFECYCLE.signal(());
    }

    fn configured(&mut self, configured: bool) {
        CONFIGURED.lock(|value| value.set(configured));
        LIFECYCLE.signal(());
    }
}

/// Called by a board task spawned on the high-priority interrupt executor.
///
/// Constructing the non-Send device here keeps CDC's RefCells in one executor.
/// The concrete board task's only argument is its Send USB peripheral token.
pub async fn run(
    usb: Peri<'static, USB>,
    irqs: impl Binding<USBCTRL_IRQ, InterruptHandler<USB>> + 'static,
) -> ! {
    let driver = Driver::new(usb, irqs);
    let mut config = Config::new(0x16c0, 0x27dd);
    config.manufacturer = Some("Displaitor");
    config.product = Some("Displaitor Canvas");
    config.serial_number = Some("canvas-1");
    config.max_packet_size_0 = 64;
    let mut config_descriptor = [0; 256];
    let mut bos_descriptor = [0; 32];
    let mut msos_descriptor = [];
    let mut control_buffer = [0; 64];
    let mut state = State::new();
    let mut lifecycle = Lifecycle;
    let mut builder = Builder::new(
        driver,
        config,
        &mut config_descriptor,
        &mut bos_descriptor,
        &mut msos_descriptor,
        &mut control_buffer,
    );
    builder.handler(&mut lifecycle);
    let class = CdcAcmClass::new(&mut builder, &mut state, PACKET_BYTES as u16);
    let mut device = builder.build();
    join(device.run(), transport(class)).await;
    unreachable!()
}

/// Drop a packet already queued while CDC is closed. The RP USB driver has
/// one OUT packet buffer. A canceled pending read has no side effects.
async fn discard_ready<'d>(receiver: &mut Receiver<'d, Driver<'d, USB>>) {
    let mut bytes = [0; PACKET_BYTES];
    let read = async {
        receiver.wait_connection().await;
        let _ = receiver.read_packet(&mut bytes).await;
    };
    let mut read = core::pin::pin!(read);
    core::future::poll_fn(|cx| {
        let _ = read.as_mut().poll(cx);
        Poll::Ready(())
    })
    .await;
}

async fn transport<'d>(class: CdcAcmClass<'d, Driver<'d, USB>>) {
    let (mut sender, mut receiver, control) = class.split_with_control();
    // Each consumed packet is retained outside the cancelable operation future.
    let mut incoming: Option<Packet> = None;
    let mut outgoing: Option<Reply> = None;
    let mut written: Option<Written> = None;
    loop {
        let operation = async {
            if let Some(ack) = written {
                BRIDGE.written.send(ack).await;
                written = None;
                return;
            }
            if let Some(reply) = outgoing {
                sender.wait_connection().await;
                if sender.write_packet(&reply.bytes[..reply.len]).await.is_ok() {
                    written = Some(Written {
                        generation: reply.generation,
                        len: reply.len,
                    });
                } else {
                    BRIDGE.new_session(false);
                }
                outgoing = None;
                return;
            }
            if let Some(packet) = incoming {
                // Keep servicing replies when a pipelining host has filled
                // ingress. The UI may be waiting for TX before draining RX.
                match BRIDGE.forward_incoming(packet).await {
                    Either::First(reply) => {
                        let current = BRIDGE.session();
                        if current.open && reply.generation == current.generation {
                            outgoing = Some(reply);
                        }
                    }
                    Either::Second(()) => incoming = None,
                }
                return;
            }
            let mut bytes = [0; PACKET_BYTES];
            let read = async {
                receiver.wait_connection().await;
                receiver.read_packet(&mut bytes).await
            };
            match select(BRIDGE.outgoing.receive(), read).await {
                Either::First(reply) => {
                    let current = BRIDGE.session();
                    if current.open && reply.generation == current.generation {
                        outgoing = Some(reply);
                    }
                }
                Either::Second(Ok(len)) => {
                    let current = BRIDGE.session();
                    if current.open && len != 0 {
                        incoming = Some(Packet {
                            generation: current.generation,
                            bytes,
                            len,
                        });
                    }
                }
                Either::Second(Err(_)) => {
                    BRIDGE.new_session(false);
                }
            }
        };
        match select3(control.control_changed(), LIFECYCLE.wait(), operation).await {
            Either3::First(()) | Either3::Second(()) => {
                // A notification can coalesce close+reopen: always abort the
                // previous generation, even if the latest DTR is still true.
                incoming = None;
                outgoing = None;
                written = None;
                let configured = CONFIGURED.lock(Cell::get);
                if configured && !control.dtr() {
                    discard_ready(&mut receiver).await;
                }
                // Do not drain on open: the supported client submits Abort as
                // soon as open returns. Already queued OUT bytes carry no
                // session timestamp, so a coalesced close+open cannot identify
                // old bytes still in the hardware bank. Software queues are
                // always discarded by generation; closed sessions drain OUT.
                BRIDGE.new_session(configured && control.dtr());
            }
            Either3::Third(()) => {}
        }
        // Let device.run() process control transfers before another data step.
        yield_now().await;
    }
}
