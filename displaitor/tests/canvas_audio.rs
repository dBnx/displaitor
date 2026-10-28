use core::time::Duration;
use displaitor::{
    AppId, AudioId, Controls, Engine, Screen,
    canvas_protocol::{self, Endpoint, Receiver},
};

fn packet(command: u8, payload: &[u8]) -> Vec<u8> {
    let mut raw = vec![1, command, 1, 0];
    raw.extend(payload);
    raw.extend(canvas_protocol::crc32(&raw).to_le_bytes());
    let mut wire = vec![0; raw.len() + 3];
    let len = canvas_protocol::encode(&raw, &mut wire).unwrap();
    wire.truncate(len);
    wire
}

fn send(engine: &mut Engine, command: u8, payload: &[u8]) -> u8 {
    let mut receiver = Receiver::new();
    let mut status = None;
    for byte in packet(command, payload) {
        if let Some(reply) = receiver.feed(byte, engine.canvas_mut()) {
            status = Some(reply.status);
        }
    }
    status.unwrap()
}

fn update(engine: &mut Engine) -> Option<AudioId> {
    engine.update(Duration::ZERO, Controls::default()).audio
}

#[test]
fn cries_are_bounded_one_shot_effects_without_remote_navigation() {
    let mut engine = Engine::new();
    assert_eq!(send(&mut engine, 11, &[1]), 0);
    assert_eq!(update(&mut engine), None);
    assert_eq!(engine.screen(), Screen::Splash);
    let _ = engine.open_canvas();
    for (id, expected) in [
        (1, AudioId::CryTorchic),
        (2, AudioId::CryEevee),
        (3, AudioId::CryTreecko),
        (0, AudioId::Stop),
    ] {
        assert_eq!(send(&mut engine, 11, &[id]), 0);
        assert_eq!(update(&mut engine), Some(expected));
        assert_eq!(update(&mut engine), None);
    }
    for invalid in [&[][..], &[4], &[255], &[1, 2]] {
        assert_eq!(send(&mut engine, 11, invalid), 4);
        assert_eq!(update(&mut engine), None);
    }
}

#[test]
fn cry_commits_with_its_scene_and_abort_or_failed_staging_stays_silent() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    assert_eq!(send(&mut engine, 7, &[]), 0);
    assert_eq!(send(&mut engine, 11, &[1]), 0);
    assert_eq!(update(&mut engine), None);
    assert_eq!(send(&mut engine, 8, &[]), 0);
    assert_eq!(update(&mut engine), Some(AudioId::CryTorchic));
    for fail in [false, true] {
        assert_eq!(send(&mut engine, 7, &[]), 0);
        assert_eq!(send(&mut engine, 11, &[2]), 0);
        if fail {
            assert_eq!(send(&mut engine, 11, &[99]), 4);
            assert_eq!(send(&mut engine, 8, &[]), 7);
        }
        assert_eq!(send(&mut engine, 9, &[]), 0);
        assert_eq!(update(&mut engine), None);
    }
}

#[test]
fn local_back_cancels_audio_even_before_the_remote_batch_cutoff() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    assert_eq!(send(&mut engine, 11, &[3]), 0);
    assert_eq!(
        engine
            .update_local(Duration::ZERO, Controls::default())
            .audio,
        None
    );
    assert_eq!(update(&mut engine), Some(AudioId::CryTreecko));
    assert_eq!(send(&mut engine, 11, &[1]), 0);
    let back = engine.update_local(
        Duration::ZERO,
        Controls {
            buttons_b: true,
            ..Controls::default()
        },
    );
    assert_eq!(back.audio, Some(AudioId::Stop));
    assert!(matches!(engine.screen(), Screen::Menu(_)));
    assert_eq!(update(&mut engine), None);
    let _ = engine.open_canvas();
    assert_eq!(engine.screen(), Screen::App(AppId::Canvas));
    assert_eq!(update(&mut engine), None);
}

#[test]
fn session_reset_discards_ready_and_staged_cries() {
    let mut engine = Engine::new();
    let _ = engine.open_canvas();
    for transaction in [false, true] {
        if transaction {
            assert_eq!(send(&mut engine, 7, &[]), 0);
        }
        assert_eq!(send(&mut engine, 11, &[2]), 0);
        Endpoint::new().reset(engine.canvas_mut());
        assert_eq!(update(&mut engine), None);
        assert_eq!(send(&mut engine, 8, &[]), 7);
        assert_eq!(update(&mut engine), None);
    }
}
