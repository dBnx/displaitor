use aitos::audio::{OUTPUT_RATE, OutputPlayer, Player};
use displaitor::AudioId;

const CRIES: [AudioId; 3] = [AudioId::CryTorchic, AudioId::CryEevee, AudioId::CryTreecko];

#[test]
fn bundled_cries_decode_fully_with_headroom_and_stop_without_looping() {
    for id in CRIES {
        let file = id.file().unwrap();
        assert!(file.len() < 6000);
        assert_eq!(file[8], 1); // Mono QOA frame.
        let declared = u32::from_be_bytes(file[4..8].try_into().unwrap());
        let mut player = Player::default();
        player.select(id).unwrap();
        assert_eq!(player.sample_rate(), Some(16_384));
        let mut count = 0;
        let mut peak = 0;
        while let Some(sample) = player.next_sample().unwrap() {
            peak = peak.max(i32::from(sample).abs());
            count += 1;
            assert!(count <= declared);
        }
        assert_eq!(count, declared);
        assert!((3000..18000).contains(&peak), "{id:?}: peak {peak}");
        assert_eq!(player.next_sample().unwrap(), None);
    }
}

#[test]
fn repeated_play_restarts_and_muting_does_not_queue_a_cry_for_later() {
    for id in CRIES {
        let mut player = OutputPlayer::new(OUTPUT_RATE);
        player.select(id).unwrap();
        let first: Vec<_> = (0..2048).map(|_| player.next_sample().unwrap()).collect();
        player.select(id).unwrap();
        let replay: Vec<_> = (0..2048).map(|_| player.next_sample().unwrap()).collect();
        assert_eq!(first, replay);
        player.set_enabled(false);
        player.set_enabled(true);
        assert!(!player.is_playing());
        player.set_enabled(false);
        player.select(id).unwrap();
        player.set_enabled(true);
        assert_eq!(player.next_sample().unwrap(), None);
        player.select(id).unwrap();
        assert!(player.is_playing());
    }
}
