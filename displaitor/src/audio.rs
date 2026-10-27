/// Audio commands. Unsupported legacy IDs have no corresponding source asset.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AudioId {
    Stop,
    BootUp,
    Ping,
    Pong,
    Nom,
    GameOver,
    MusicDepp,
    MusicTetris,
    MusicPPAP,
    MusicPen,
    MusicNyan,
}

impl AudioId {
    pub const fn file(self) -> Option<&'static [u8]> {
        match self {
            Self::Ping => Some(include_bytes!("../../assets/audio/ping.qoa")),
            Self::Pong => Some(include_bytes!("../../assets/audio/pong.qoa")),
            Self::MusicTetris => Some(include_bytes!("../../assets/audio/music_tetris.qoa")),
            Self::MusicPPAP | Self::MusicPen => {
                Some(include_bytes!("../../assets/audio/music_ppap.qoa"))
            }
            Self::MusicNyan => Some(include_bytes!("../../assets/audio/music_nyan_cat.qoa")),
            _ => None,
        }
    }

    pub const fn into_audio_file(&self) -> Option<&'static [u8]> {
        self.file()
    }
}
