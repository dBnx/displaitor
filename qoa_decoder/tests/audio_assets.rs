use qoa_decoder::QoaDecoder;

const AUDIO_ASSETS: &[(&str, &[u8])] = &[
    (
        "cry_torchic.qoa",
        include_bytes!("../../assets/audio/cry_torchic.qoa"),
    ),
    (
        "cry_eevee.qoa",
        include_bytes!("../../assets/audio/cry_eevee.qoa"),
    ),
    (
        "cry_treecko.qoa",
        include_bytes!("../../assets/audio/cry_treecko.qoa"),
    ),
    ("ping.qoa", include_bytes!("../../assets/audio/ping.qoa")),
    ("pong.qoa", include_bytes!("../../assets/audio/pong.qoa")),
    (
        "music_nyan_cat.qoa",
        include_bytes!("../../assets/audio/music_nyan_cat.qoa"),
    ),
    (
        "music_tetris.qoa",
        include_bytes!("../../assets/audio/music_tetris.qoa"),
    ),
    (
        "music_ppap.qoa",
        include_bytes!("../../assets/audio/music_ppap.qoa"),
    ),
];

#[test]
fn every_linked_qoa_asset_decodes_to_its_declared_sample_count() {
    for &(name, bytes) in AUDIO_ASSETS {
        let declared = u32::from_be_bytes(bytes[4..8].try_into().unwrap());
        let mut decoder = QoaDecoder::new(bytes).unwrap_or_else(|error| {
            panic!("{name}: decoder rejected asset: {error:?}");
        });
        assert!(decoder.sample_rate() > 0, "{name}: zero sample rate");

        let mut decoded = 0u32;
        loop {
            match decoder.try_next_sample() {
                Ok(Some(_)) => decoded += 1,
                Ok(None) => break,
                Err(error) => panic!("{name}: decode failed after {decoded} samples: {error:?}"),
            }
        }
        assert_eq!(decoded, declared, "{name}: decoded sample count mismatch");
    }
}

#[test]
fn matches_upstream_pcm_across_nonzero_lms_and_frame_boundary() {
    const QOA: &[u8] = include_bytes!("fixtures/nonzero_lms_two_frames.qoa");
    const PCM: &[u8] = include_bytes!("fixtures/nonzero_lms_two_frames.pcm16le");

    assert_eq!(u32::from_be_bytes(QOA[4..8].try_into().unwrap()), 5_257);
    let first_frame_size = u16::from_be_bytes([QOA[14], QOA[15]]) as usize;
    let second_frame = 8 + first_frame_size;
    assert_eq!(u16::from_be_bytes([QOA[12], QOA[13]]), 5_120);
    assert_eq!(
        u16::from_be_bytes([QOA[second_frame + 4], QOA[second_frame + 5]]),
        137
    );
    assert!(
        QOA[second_frame + 8..second_frame + 24]
            .iter()
            .any(|byte| *byte != 0)
    );
    assert_eq!(PCM.len(), 5_257 * 2);

    let mut decoder = QoaDecoder::new(QOA).unwrap();
    for (index, expected_bytes) in PCM.as_chunks::<2>().0.iter().enumerate() {
        let expected = i16::from_le_bytes([expected_bytes[0], expected_bytes[1]]);
        assert_eq!(
            decoder.try_next_sample(),
            Ok(Some(expected)),
            "reference PCM mismatch at sample {index}"
        );
    }
    assert_eq!(decoder.try_next_sample(), Ok(None));
}
