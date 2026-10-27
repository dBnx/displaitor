use core::time::Duration;
use displaitor::{
    AppId, Controls, Engine, Screen,
    canvas::{Canvas, Error},
    canvas_input::{CANVAS_ACTIVE, FLAG_LOST, FLAG_MORE},
    canvas_protocol::{self, Endpoint, MAX_REPLY, Receiver, Reply},
};

fn request(command: u8, sequence: u16, payload: &[u8]) -> Vec<u8> {
    let mut raw = vec![1, command];
    raw.extend(sequence.to_le_bytes());
    raw.extend(payload);
    raw.extend(canvas_protocol::crc32(&raw).to_le_bytes());
    let mut wire = vec![0; raw.len() + 2];
    let len = canvas_protocol::encode(&raw, &mut wire).unwrap();
    wire.truncate(len);
    wire
}

fn send(canvas: &mut Canvas, command: u8, payload: &[u8]) -> Reply {
    let mut receiver = Receiver::new();
    request(command, 0x4321, payload)
        .into_iter()
        .find_map(|byte| receiver.feed(byte, canvas))
        .unwrap()
}

fn decode(wire: &[u8]) -> Vec<u8> {
    assert_eq!(wire.last(), Some(&0));
    let mut raw = Vec::new();
    let mut pos = 0;
    while pos < wire.len() - 1 {
        let code = usize::from(wire[pos]);
        pos += 1;
        raw.extend_from_slice(&wire[pos..pos + code - 1]);
        pos += code - 1;
        if code != 255 && pos < wire.len() - 1 {
            raw.push(0);
        }
    }
    let crc_at = raw.len() - 4;
    assert_eq!(
        canvas_protocol::crc32(&raw[..crc_at]),
        u32::from_le_bytes(raw[crc_at..].try_into().unwrap())
    );
    raw
}

#[test]
fn baseline_and_quick_press_release_page_without_consuming_or_phantom_events() {
    let mut engine = Engine::new();
    assert_eq!(engine.canvas().buttons(None).latest, 0);
    let _ = engine.open_canvas();
    let baseline = send(engine.canvas_mut(), 10, &[]).buttons.unwrap();
    assert_eq!(
        (baseline.state, baseline.latest, baseline.count),
        (0x80, 1, 0)
    );
    for index in 0..6 {
        let _ = engine.update(
            Duration::from_micros(1_500),
            Controls {
                buttons_a: index % 2 == 0,
                ..Controls::default()
            },
        );
    }
    let cursor = baseline.latest.to_le_bytes();
    let first = send(engine.canvas_mut(), 10, &cursor).buttons.unwrap();
    assert_eq!(
        (first.count, first.flags, first.latest, first.now_ms),
        (4, FLAG_MORE, 7, 9)
    );
    assert_eq!(
        first.events.map(|event| event.state),
        [0x81, 0x80, 0x81, 0x80]
    );
    assert_eq!(first.events.map(|event| event.at_ms), [1, 3, 4, 6]);
    assert_eq!(
        send(engine.canvas_mut(), 10, &cursor).buttons.unwrap(),
        first
    );
    let second = engine.canvas().buttons(Some(first.events[3].id));
    assert_eq!((second.count, second.flags), (2, 0));
    assert_eq!((second.events[0].id, second.events[1].id), (6, 7));
    let reconnect = send(engine.canvas_mut(), 10, &[]).buttons.unwrap();
    assert_eq!(
        (reconnect.latest, reconnect.count, reconnect.flags),
        (7, 0, 0)
    );
}

#[test]
fn overflow_future_and_half_range_cursors_resynchronize_without_partial_events() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    for index in 0..40 {
        let _ = engine.update(
            Duration::from_millis(1),
            Controls {
                dpad_right: index % 2 == 0,
                ..Controls::default()
            },
        );
    }
    let baseline = engine.canvas().buttons(None);
    assert_eq!((baseline.latest, baseline.overwritten), (41, 9));
    for cursor in [0, 8, 42, baseline.latest.wrapping_sub(0x8000_0000)] {
        let report = engine.canvas().buttons(Some(cursor));
        assert_eq!(
            (report.flags, report.count, report.latest, report.state),
            (FLAG_LOST, 0, 41, CANVAS_ACTIVE)
        );
    }
    let oldest = engine.canvas().buttons(Some(9));
    assert_eq!(
        (oldest.events[0].id, oldest.count, oldest.flags),
        (10, 4, FLAG_MORE)
    );
    let current = engine.canvas().buttons(Some(41));
    assert_eq!((current.flags, current.count), (0, 0));
}

#[test]
fn local_back_wins_and_all_update_paths_record_the_final_mode_and_buttons() {
    let mut engine = Engine::new();
    let _ = engine.update(
        Duration::from_millis(2),
        Controls {
            buttons_a: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.canvas().buttons(None).state, 1); // Splash early return paths still record.
    let _ = engine.open_canvas();
    assert_eq!(engine.canvas().buttons(None).state, 0x81); // Active before another update.
    engine.request_canvas();
    let _ = engine.update_local(
        Duration::from_millis(1),
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert!(matches!(engine.screen(), Screen::Menu(_)));
    assert_eq!(engine.canvas().buttons(None).state, 2);
    let _ = engine.update(Duration::from_millis(1), Controls::default());
    assert!(matches!(engine.screen(), Screen::Menu(_))); // Back cleared pending Show.
    engine.request_canvas();
    let _ = engine.update(Duration::from_millis(1), Controls::default());
    assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
    assert_eq!(engine.canvas().buttons(None).state, CANVAS_ACTIVE);
    assert_eq!(engine.canvas().buttons(None).now_ms, 5);
    assert_eq!(engine.next_update_after(), None);
    let _ = engine.update(
        Duration::ZERO,
        Controls {
            buttons_a: true,
            buttons_s: true,
            dpad_up: true,
            dpad_down: true,
            dpad_left: true,
            dpad_right: true,
            ..Controls::default()
        },
    );
    assert_eq!(engine.canvas().buttons(None).state, 0xfd);
}

#[test]
fn reset_and_scene_transactions_preserve_input_history() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    let _ = engine.update(
        Duration::from_millis(7),
        Controls {
            dpad_left: true,
            ..Controls::default()
        },
    );
    let before = engine.canvas().buttons(Some(0));
    let mut endpoint = Endpoint::new();
    for byte in request(10, 2, &0_u32.to_le_bytes()) {
        assert!(endpoint.receive(byte, engine.canvas_mut()));
    }
    endpoint.reset(engine.canvas_mut()); // Simulates losing the first reply.
    assert_eq!(engine.canvas().buttons(Some(0)), before);
    for command in [7, 5, 8, 7, 9] {
        let payload = if command == 5 { &[0, 0][..] } else { &[] };
        assert_eq!(send(engine.canvas_mut(), command, payload).status, 0);
        assert_eq!(engine.canvas().buttons(Some(0)), before);
    }
    engine.canvas_mut().apply(7, &[]).unwrap();
    assert!(engine.canvas_mut().apply(2, &[]).is_err());
    assert_eq!(
        send(engine.canvas_mut(), 10, &[]).buttons.unwrap().latest,
        2
    );
    assert_eq!(engine.canvas().buttons(Some(0)), before);
}

#[test]
fn button_wire_shape_crc_bounds_and_invalid_payload_leave_ack_compatible() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    for index in 0..4 {
        let _ = engine.update(
            Duration::from_millis(5),
            Controls {
                dpad_left: index % 2 == 0,
                ..Controls::default()
            },
        );
    }
    let mut wire = [0; MAX_REPLY];
    let reply = send(engine.canvas_mut(), 10, &1_u32.to_le_bytes());
    let len = reply.encode(&mut wire);
    assert_eq!(len, 62);
    let raw = decode(&wire[..len]);
    assert_eq!(raw.len(), 60);
    assert_eq!(&raw[..8], &[1, 0x81, 0x21, 0x43, 0, 0x80, 0, 4]);
    assert_eq!(&raw[8..20], &[5, 0, 0, 0, 0, 0, 0, 0, 20, 0, 0, 0]);
    assert_eq!(&raw[20..29], &[2, 0, 0, 0, 5, 0, 0, 0, 0xa0]);
    assert_eq!(&raw[47..56], &[5, 0, 0, 0, 20, 0, 0, 0, 0x80]);
    let baseline = send(engine.canvas_mut(), 10, &[]);
    let len = baseline.encode(&mut wire);
    assert_eq!(decode(&wire[..len]).len(), 24);
    for size in [1, 2, 3, 5] {
        let reply = send(engine.canvas_mut(), 10, &vec![0; size]);
        assert_eq!(reply.status, Error::Value as u8);
        assert!(reply.buttons.is_none());
        let len = reply.encode(&mut wire);
        let raw = decode(&wire[..len]);
        assert_eq!(raw.len(), 17);
        assert_eq!(
            &raw[..13],
            &[1, 0x80, 0x21, 0x43, 4, 64, 32, 8, 64, 0, 0, 0, 0]
        );
    }
    let normal = send(engine.canvas_mut(), 0, &[]);
    let len = normal.encode(&mut wire);
    let expected = [1, 0x80, 0x21, 0x43, 0, 64, 32, 8, 64, 0, 0, 0, 0];
    let mut expected_raw = expected.to_vec();
    expected_raw.extend(canvas_protocol::crc32(&expected).to_le_bytes());
    let mut expected_wire = [0; 20];
    let expected_len = canvas_protocol::encode(&expected_raw, &mut expected_wire).unwrap();
    assert_eq!(&wire[..len], &expected_wire[..expected_len]);
}
