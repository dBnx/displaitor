use core::{convert::Infallible, time::Duration};
use displaitor::{
    AppId, Controls, Engine, Screen,
    canvas::{Canvas, Error, FRAME_BYTES},
    canvas_protocol::{self, Endpoint, MAX_ENCODED, Receiver, Reply},
};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};

#[derive(Debug, PartialEq, Eq)]
struct Frame([u16; 2048]);
impl OriginDimensions for Frame {
    fn size(&self) -> Size {
        Size::new(64, 32)
    }
}
impl DrawTarget for Frame {
    type Color = Rgb565;
    type Error = Infallible;
    fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
        &mut self,
        pixels: I,
    ) -> Result<(), Self::Error> {
        for Pixel(p, color) in pixels {
            assert!((0..64).contains(&p.x) && (0..32).contains(&p.y));
            self.0[p.y as usize * 64 + p.x as usize] = color.into_storage();
        }
        Ok(())
    }
}
fn frame(canvas: &Canvas) -> Frame {
    let mut output = Frame([0; 2048]);
    canvas.render(&mut output).unwrap();
    output
}
fn layout(text: &[u8], opaque: bool) -> Vec<u8> {
    // ID, host-name salt, count; slot,x,y,w,h,font,fg,bg-enabled,bg,text-len,text.
    let mut bytes = vec![0; 8];
    bytes.push(1);
    bytes.extend([
        0,
        2,
        2,
        24,
        10,
        1,
        0xff,
        0xff,
        u8::from(opaque),
        0,
        0xf8,
        text.len() as u8,
    ]);
    bytes.extend(text);
    rehash(&mut bytes);
    bytes
}
fn rehash(bytes: &mut [u8]) {
    let id = canvas_protocol::crc32(&bytes[4..]);
    bytes[..4].copy_from_slice(&id.to_le_bytes());
}
fn reference(canvas: &Canvas, text: &[u8]) -> Vec<u8> {
    let mut bytes = canvas.layout_id().to_le_bytes().to_vec();
    bytes.push(0);
    bytes.extend(text);
    bytes
}
fn wire(version: u8, command: u8, sequence: u16, payload: &[u8]) -> Vec<u8> {
    let mut raw = vec![version, command];
    raw.extend(sequence.to_le_bytes());
    raw.extend(payload);
    raw.extend(canvas_protocol::crc32(&raw).to_le_bytes());
    let mut encoded = vec![0; MAX_ENCODED + 1];
    let len = canvas_protocol::encode(&raw, &mut encoded).unwrap();
    encoded.truncate(len);
    encoded
}
fn send(receiver: &mut Receiver, canvas: &mut Canvas, bytes: &[u8]) -> Option<Reply> {
    let mut reply = None;
    for &byte in bytes {
        if let Some(next) = receiver.feed(byte, canvas) {
            assert!(reply.is_none());
            reply = Some(next);
        }
    }
    reply
}

#[test]
fn setup_hint_survives_info_and_bad_packets_but_not_an_explicit_black_scene() {
    let mut canvas = Canvas::new();
    let hint = frame(&canvas);
    assert!(hint.0.iter().any(|&pixel| pixel != 0));
    assert!(hint.0.iter().filter(|&&pixel| pixel == 0).count() > 1400);
    let mut receiver = Receiver::new();
    assert_eq!(
        send(&mut receiver, &mut canvas, &wire(1, 0, 1, &[]))
            .unwrap()
            .status,
        0
    );
    assert_eq!(
        send(&mut receiver, &mut canvas, &wire(1, 6, 2, &[]))
            .unwrap()
            .status,
        0
    );
    assert_eq!(canvas.apply(1, &[0]), Err(Error::Value));
    assert_eq!(frame(&canvas), hint);
    canvas.apply(5, &[0, 0]).unwrap();
    assert!(frame(&canvas).0.iter().all(|&pixel| pixel == 0));
    canvas.apply(0, &[]).unwrap();
    assert!(frame(&canvas).0.iter().all(|&pixel| pixel == 0));
}

#[test]
fn full_background_commits_only_after_complete_valid_packet() {
    let mut canvas = Canvas::new();
    canvas.apply(5, &0xf800_u16.to_le_bytes()).unwrap();
    let before = frame(&canvas);
    let pixels: Vec<u8> = (0..2048_u16).flat_map(u16::to_le_bytes).collect();
    let message = wire(1, 1, 17, &pixels);
    let mut receiver = Receiver::new();
    for &byte in &message[..message.len() - 1] {
        assert!(receiver.feed(byte, &mut canvas).is_none());
    }
    assert_eq!(frame(&canvas), before);
    let reply = receiver.feed(0, &mut canvas).unwrap();
    assert_eq!((reply.sequence, reply.status), (17, 0));
    assert_eq!(frame(&canvas).0, core::array::from_fn(|i| i as u16));
}

#[test]
fn corruption_oversize_and_truncation_do_not_change_scene_and_resynchronize() {
    let mut canvas = Canvas::new();
    let mut receiver = Receiver::new();
    let before = frame(&canvas);
    let valid = wire(1, 5, 42, &[0, 0xf8]);
    let mut bad = valid.clone();
    bad[3] ^= 0x10;
    assert!(send(&mut receiver, &mut canvas, &bad).is_none());
    let mut huge = vec![1; MAX_ENCODED + 100];
    huge.push(0);
    assert!(send(&mut receiver, &mut canvas, &huge).is_none());
    for cut in 1..valid.len() - 1 {
        receiver.reset();
        assert!(send(&mut receiver, &mut canvas, &valid[..cut]).is_none());
        receiver.reset();
    }
    assert_eq!(frame(&canvas), before);
    assert_eq!(send(&mut receiver, &mut canvas, &valid).unwrap().status, 0);
    assert!(frame(&canvas).0.iter().all(|&p| p == 0xf800));
}

#[test]
fn transparent_and_solid_boxes_and_foreground_colours_are_independent() {
    let mut canvas = Canvas::new();
    canvas.apply(5, &[0x1f, 0]).unwrap(); // blue background
    canvas.apply(2, &layout(b"A", false)).unwrap();
    let transparent = frame(&canvas);
    assert!(transparent.0.contains(&0xffff));
    assert!(transparent.0.iter().all(|&p| p == 0x001f || p == 0xffff));
    // Green glyphs on a red opaque box, retaining the image outside the box.
    canvas
        .apply(4, &reference(&canvas, &[0xe0, 7, 1, 0, 0xf8]))
        .unwrap();
    let opaque = frame(&canvas);
    assert!(!opaque.0.contains(&0xffff));
    assert!(opaque.0.contains(&0x07e0));
    for y in 0..32 {
        for x in 0..64 {
            let pixel = opaque.0[y * 64 + x];
            if (2..26).contains(&x) && (2..12).contains(&y) {
                assert!(pixel == 0xf800 || pixel == 0x07e0);
            } else {
                assert_eq!(pixel, 0x001f);
            }
        }
    }
    canvas.apply(3, &reference(&canvas, b"")).unwrap();
    let empty = frame(&canvas);
    assert!(empty.0.contains(&0xf800)); // opaque box remains with empty content
    canvas
        .apply(4, &reference(&canvas, &[0xe0, 7, 0, 0, 0]))
        .unwrap();
    assert!(frame(&canvas).0.iter().all(|&p| p == 0x001f));
}

#[test]
fn shorter_text_and_new_background_leave_no_old_glyphs() {
    let mut canvas = Canvas::new();
    canvas.apply(2, &layout(b"100", false)).unwrap();
    assert!(frame(&canvas).0.contains(&0xffff));
    canvas.apply(3, &reference(&canvas, b"9")).unwrap();
    let mut fresh = Canvas::new();
    fresh.apply(2, &layout(b"9", false)).unwrap();
    assert_eq!(frame(&canvas), frame(&fresh));
    canvas.apply(5, &[0x1f, 0]).unwrap();
    fresh.apply(5, &[0x1f, 0]).unwrap();
    assert_eq!(frame(&canvas), frame(&fresh));
    canvas.apply(3, &reference(&canvas, b"")).unwrap();
    assert!(frame(&canvas).0.iter().all(|&p| p == 0x1f));
}

#[test]
fn invalid_layouts_are_atomic_including_duplicate_slots_and_trailing_data() {
    let mut canvas = Canvas::new();
    let valid = layout(b"OK", false);
    canvas.apply(2, &valid).unwrap();
    let before = frame(&canvas);
    let id = canvas.layout_id();
    for end in 0..valid.len() {
        assert!(canvas.apply(2, &valid[..end]).is_err());
    }
    for (index, value) in [
        (8, 9),
        (9, 8),
        (10, 64),
        (11, 32),
        (12, 0),
        (12, 63),
        (13, 0),
        (14, 3),
        (17, 2),
        (20, 65),
    ] {
        let mut bad = valid.clone();
        bad[index] = value;
        rehash(&mut bad);
        assert!(canvas.apply(2, &bad).is_err(), "index {index}");
    }
    let mut duplicate = valid.clone();
    duplicate[8] = 2;
    duplicate.extend_from_slice(&valid[9..]);
    rehash(&mut duplicate);
    assert!(canvas.apply(2, &duplicate).is_err());
    let mut trailing = valid.clone();
    trailing.push(0);
    rehash(&mut trailing);
    assert!(canvas.apply(2, &trailing).is_err());
    assert_eq!(canvas.layout_id(), id);
    assert_eq!(frame(&canvas), before);
}

#[test]
fn invalid_text_style_and_stale_references_leave_scene_intact() {
    let mut canvas = Canvas::new();
    canvas.apply(2, &layout("18°C".as_bytes(), false)).unwrap();
    let before = frame(&canvas);
    for text in [
        vec![b'A'; 65],
        vec![0xff],
        vec![b'\n'],
        "🦀".as_bytes().to_vec(),
    ] {
        assert_eq!(
            canvas.apply(3, &reference(&canvas, &text)),
            Err(Error::Text)
        );
    }
    let mut stale = reference(&canvas, b"wrong");
    stale[0] ^= 1;
    assert_eq!(canvas.apply(3, &stale), Err(Error::Layout));
    assert!(
        canvas
            .apply(4, &reference(&canvas, &[0xff, 0xff, 2, 0, 0]))
            .is_err()
    );
    assert!(canvas.apply(4, &reference(&canvas, &[0xff])).is_err());
    let mut slot = reference(&canvas, b"wrong");
    slot[4] = 7;
    assert_eq!(canvas.apply(3, &slot), Err(Error::Value));
    assert_eq!(frame(&canvas), before);
}

#[test]
fn ordinary_commands_and_errors_are_acknowledged_without_screen_control() {
    let mut canvas = Canvas::new();
    let before = frame(&canvas);
    let mut receiver = Receiver::new();
    for (version, command, status) in [(2, 5, 2), (1, 99, 3), (1, 1, 4), (1, 0, 0)] {
        let reply = send(
            &mut receiver,
            &mut canvas,
            &wire(version, command, 0x4321, &[]),
        )
        .unwrap();
        assert_eq!((reply.sequence, reply.status), (0x4321, status));
        assert!(!reply.show_canvas);
    }
    assert_eq!(frame(&canvas), before);
    assert_eq!(canvas_protocol::crc32(b"123456789"), 0xcbf4_3926);
}

#[test]
fn explicit_show_requires_valid_version_crc_and_empty_payload_and_resets() {
    let mut endpoint = Endpoint::new();
    let mut canvas = Canvas::new();
    for (version, payload) in [(2, &[][..]), (1, &[0][..])] {
        for byte in wire(version, 6, 1, payload) {
            assert!(endpoint.receive(byte, &mut canvas));
        }
        assert!(!endpoint.take_show_request());
        endpoint.written(usize::MAX);
    }
    let mut corrupt = wire(1, 6, 2, &[]);
    corrupt[3] ^= 0x10;
    for byte in corrupt {
        let _ = endpoint.receive(byte, &mut canvas);
    }
    assert!(endpoint.pending().is_empty());
    assert!(!endpoint.take_show_request());
    for byte in wire(1, 6, 3, &[]) {
        assert!(endpoint.receive(byte, &mut canvas));
    }
    assert!(endpoint.take_show_request());
    assert!(!endpoint.take_show_request());
    assert!(!endpoint.receive(0, &mut canvas)); // Reply still applies backpressure.
    endpoint.written(usize::MAX);
    for byte in wire(1, 6, 4, &[]) {
        assert!(endpoint.receive(byte, &mut canvas));
    }
    endpoint.reset(&mut canvas);
    assert!(!endpoint.take_show_request());
}

#[test]
fn requested_canvas_launch_uses_update_effects_retains_scene_and_respects_local_back() {
    let mut engine = Engine::new();
    engine.canvas_mut().apply(5, &[0xe0, 7]).unwrap();
    engine.request_canvas();
    assert_eq!(engine.screen(), Screen::Splash); // Queued until the owning update.
    let update = engine.update(Duration::ZERO, Controls::default());
    assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
    assert!(update.redraw);
    assert_eq!(update.audio, Some(displaitor::AudioId::Stop));
    let _ = engine.update(Duration::ZERO, Controls::default()); // Consume scene dirty.
    engine.request_canvas();
    let idle = engine.update(Duration::ZERO, Controls::default());
    assert!(!idle.redraw);
    assert_eq!(idle.audio, None);
    assert!(frame(engine.canvas()).0.iter().all(|&p| p == 0x07e0));

    engine.request_canvas();
    let _ = engine.update(
        Duration::ZERO,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert!(matches!(engine.screen(), Screen::Menu(_)));
    let _ = engine.update(Duration::ZERO, Controls::default());
    assert!(matches!(engine.screen(), Screen::Menu(_))); // No deferred takeover.
}

#[test]
fn endpoint_backpressure_partial_writes_and_reset_preserve_scene() {
    let mut endpoint = Endpoint::new();
    let mut canvas = Canvas::new();
    for byte in wire(1, 5, 7, &[0xe0, 7]) {
        assert!(endpoint.receive(byte, &mut canvas));
    }
    let reply = endpoint.pending().to_vec();
    assert!(!reply.is_empty());
    assert!(!endpoint.receive(42, &mut canvas));
    endpoint.written(3);
    assert_eq!(endpoint.pending(), &reply[3..]);
    endpoint.written(usize::MAX);
    assert!(endpoint.pending().is_empty());
    let before = frame(&canvas);
    for byte in wire(1, 5, 8, &[0, 0xf8]).into_iter().take(4) {
        endpoint.receive(byte, &mut canvas);
    }
    endpoint.reset(&mut canvas);
    for byte in wire(1, 0, 9, &[]) {
        assert!(endpoint.receive(byte, &mut canvas));
    }
    assert!(!endpoint.pending().is_empty());
    assert_eq!(frame(&canvas), before);
}

#[test]
fn reception_does_not_navigate_and_scene_survives_local_back() {
    let mut engine = Engine::new();
    let original = engine.screen();
    engine.canvas_mut().apply(5, &[0xe0, 7]).unwrap();
    assert_eq!(engine.screen(), original);
    let _ = engine.open_canvas();
    assert!(engine.update(Duration::ZERO, Controls::default()).redraw);
    assert!(!engine.update(Duration::ZERO, Controls::default()).redraw);
    let update = engine.update(
        Duration::ZERO,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert!(update.redraw);
    assert!(matches!(engine.screen(), Screen::Menu(_)));
    let _ = engine.update(Duration::ZERO, Controls::default());
    engine.canvas_mut().apply(5, &[0x1f, 0]).unwrap();
    assert!(!engine.update(Duration::ZERO, Controls::default()).redraw);
    let _ = engine.open_canvas();
    assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
    assert!(frame(engine.canvas()).0.iter().all(|&p| p == 0x1f));
}

#[test]
fn malformed_network_input_is_bounded_and_recovers() {
    let mut receiver = Receiver::new();
    let mut canvas = Canvas::new();
    let mut random = 0x1234abcd_u32;
    for _ in 0..500 {
        for _ in 0..127 {
            random ^= random << 13;
            random ^= random >> 17;
            random ^= random << 5;
            let _ = receiver.feed(random as u8, &mut canvas);
        }
        let _ = receiver.feed(0, &mut canvas);
    }
    let full = wire(1, 1, 12, &vec![0xff; FRAME_BYTES]); // worst-case COBS block lengths
    assert_eq!(send(&mut receiver, &mut canvas, &full).unwrap().status, 0);
    assert_eq!(frame(&canvas), Frame([0xffff; 2048]));
}

#[test]
fn maximum_slots_text_and_all_fonts_clip_at_the_screen_edge_in_slot_order() {
    let mut canvas = Canvas::new();
    let mut config = vec![0; 8];
    config.push(8);
    for slot in 0..8 {
        config.extend([slot, 63, 31, 1, 1, slot % 3, 0xff, 0xff, 1, slot, 0, 64]);
        config.extend([b'W'; 64]);
    }
    rehash(&mut config);
    canvas.apply(2, &config).unwrap();
    let pixels = frame(&canvas).0;
    assert!(pixels[..2047].iter().all(|&p| p == 0));
    // All boxes overlap; the last slot's opaque fill wins at the only visible pixel.
    assert!(pixels[2047] == 7 || pixels[2047] == 0xffff);
    let mut last = canvas.layout_id().to_le_bytes().to_vec();
    last.push(7);
    canvas.apply(3, &last).unwrap();
    assert_eq!(frame(&canvas).0[2047], 7);
}

#[test]
fn canvas_propagates_draw_errors() {
    struct Broken;
    impl DrawTarget for Broken {
        type Color = Rgb565;
        type Error = &'static str;
        fn draw_iter<I: IntoIterator<Item = Pixel<Rgb565>>>(
            &mut self,
            _: I,
        ) -> Result<(), Self::Error> {
            Err("broken")
        }
    }
    impl OriginDimensions for Broken {
        fn size(&self) -> Size {
            Size::new(64, 32)
        }
    }
    assert_eq!(Canvas::new().render(&mut Broken), Err("broken"));
}

fn exchange(
    endpoint: &mut Endpoint,
    canvas: &mut Canvas,
    command: u8,
    payload: &[u8],
) -> (u8, u32, bool) {
    for byte in wire(1, command, 33, payload) {
        assert!(endpoint.receive(byte, canvas));
    }
    let encoded = endpoint.pending();
    let mut decoded = Vec::new();
    let mut pos = 0;
    while pos < encoded.len() - 1 {
        let code = encoded[pos] as usize;
        pos += 1;
        decoded.extend_from_slice(&encoded[pos..pos + code - 1]);
        pos += code - 1;
        if code != 255 && pos < encoded.len() - 1 {
            decoded.push(0);
        }
    }
    endpoint.written(usize::MAX);
    (
        decoded[4],
        u32::from_le_bytes(decoded[9..13].try_into().unwrap()),
        endpoint.take_show_request(),
    )
}

#[test]
fn scene_transaction_stages_all_layers_and_publishes_once_with_deferred_show() {
    let mut canvas = Canvas::new();
    let mut endpoint = Endpoint::new();
    canvas.apply(2, &layout(b"OLD", false)).unwrap();
    canvas.apply(5, &[0x1f, 0]).unwrap();
    let before = frame(&canvas);
    let old_layout = canvas.layout_id();
    assert_eq!(
        exchange(&mut endpoint, &mut canvas, 7, &[]),
        (0, old_layout, false)
    );
    let new_layout = layout(b"INITIAL", true);
    let new_id = u32::from_le_bytes(new_layout[..4].try_into().unwrap());
    let mut reference = new_id.to_le_bytes().to_vec();
    reference.push(0);
    for (command, payload) in [
        (1, vec![0xff; FRAME_BYTES]),
        (2, new_layout.clone()),
        (3, [reference.as_slice(), b"NEW"].concat()),
        (4, [reference.as_slice(), &[0xe0, 7, 1, 0, 0]].concat()),
        (6, vec![]),
    ] {
        let (status, reply_layout, show) = exchange(&mut endpoint, &mut canvas, command, &payload);
        assert_eq!(status, 0);
        assert!(!show);
        assert_eq!(canvas.layout_id(), old_layout);
        assert_eq!(reply_layout, if command == 1 { old_layout } else { new_id });
        assert_eq!(frame(&canvas), before);
    }
    assert_eq!(
        exchange(&mut endpoint, &mut canvas, 8, &[]),
        (0, new_id, true)
    );
    let mut expected = Canvas::new();
    expected.apply(1, &vec![0xff; FRAME_BYTES]).unwrap();
    expected.apply(2, &new_layout).unwrap();
    expected
        .apply(3, &[reference.as_slice(), b"NEW"].concat())
        .unwrap();
    expected
        .apply(4, &[reference.as_slice(), &[0xe0, 7, 1, 0, 0]].concat())
        .unwrap();
    assert_eq!(frame(&canvas), frame(&expected));
    assert_ne!(frame(&canvas), before);
    assert_eq!(
        exchange(&mut endpoint, &mut canvas, 8, &[]).0,
        Error::Transaction as u8
    );
}

#[test]
fn poisoned_aborted_disconnected_and_replaced_transactions_never_publish_or_show() {
    let mut canvas = Canvas::new();
    let mut endpoint = Endpoint::new();
    let hint = frame(&canvas);
    for recovery in [9, 7, 255] {
        assert_eq!(exchange(&mut endpoint, &mut canvas, 7, &[]).0, 0);
        assert_eq!(exchange(&mut endpoint, &mut canvas, 5, &[0, 0xf8]).0, 0);
        assert!(!exchange(&mut endpoint, &mut canvas, 6, &[]).2);
        assert_eq!(
            exchange(&mut endpoint, &mut canvas, 2, &[0]).0,
            Error::Value as u8
        );
        assert_eq!(
            exchange(&mut endpoint, &mut canvas, 5, &[0xe0, 7]).0,
            Error::Transaction as u8
        );
        assert_eq!(
            exchange(&mut endpoint, &mut canvas, 8, &[]).0,
            Error::Transaction as u8
        );
        assert_eq!(frame(&canvas), hint);
        if recovery == 255 {
            endpoint.reset(&mut canvas);
        } else {
            assert_eq!(exchange(&mut endpoint, &mut canvas, recovery, &[]).0, 0);
        }
        assert_eq!(frame(&canvas), hint);
        assert!(!endpoint.take_show_request());
        if recovery == 7 {
            // Begin recovered from the visible setup hint, never the discarded red scene.
            assert_eq!(exchange(&mut endpoint, &mut canvas, 8, &[]), (0, 0, false));
            assert_eq!(frame(&canvas), hint);
        }
    }
    // A reset also drops partial wire packets and pending navigation.
    assert_eq!(exchange(&mut endpoint, &mut canvas, 7, &[]).0, 0);
    assert_eq!(exchange(&mut endpoint, &mut canvas, 5, &[0xe0, 7]).0, 0);
    assert!(!exchange(&mut endpoint, &mut canvas, 6, &[]).2);
    endpoint.reset(&mut canvas);
    assert_eq!(
        exchange(&mut endpoint, &mut canvas, 8, &[]).0,
        Error::Transaction as u8
    );
    assert_eq!(frame(&canvas), hint);
    assert_eq!(exchange(&mut endpoint, &mut canvas, 7, &[]).0, 0);
    assert_eq!(exchange(&mut endpoint, &mut canvas, 5, &[0xe0, 7]).0, 0);
    assert_eq!(exchange(&mut endpoint, &mut canvas, 8, &[]), (0, 0, false));
    assert!(frame(&canvas).0.iter().all(|&p| p == 0x07e0));
}

#[test]
fn staging_does_not_trigger_engine_redraw_until_commit() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    let _ = engine.update(Duration::ZERO, Controls::default());
    engine.canvas_mut().apply(7, &[]).unwrap();
    engine.canvas_mut().apply(5, &[0xe0, 7]).unwrap();
    assert!(!engine.update(Duration::ZERO, Controls::default()).redraw);
    engine.canvas_mut().apply(8, &[]).unwrap();
    assert!(engine.update(Duration::ZERO, Controls::default()).redraw);
    assert!(!engine.update(Duration::ZERO, Controls::default()).redraw);
}
