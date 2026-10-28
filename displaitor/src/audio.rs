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
    CryTorchic,
    CryEevee,
    CryTreecko,
}

impl AudioId {
    pub const fn canvas_cry(id: u8) -> Option<Self> {
        match id {
            0 => Some(Self::Stop),
            1 => Some(Self::CryTorchic),
            2 => Some(Self::CryEevee),
            3 => Some(Self::CryTreecko),
            _ => None,
        }
    }

    pub const fn is_cry(self) -> bool {
        matches!(self, Self::CryTorchic | Self::CryEevee | Self::CryTreecko)
    }

    pub const fn file(self) -> Option<&'static [u8]> {
        match self {
            Self::Ping => Some(include_bytes!("../../assets/audio/ping.qoa")),
            Self::Pong => Some(include_bytes!("../../assets/audio/pong.qoa")),
            Self::MusicTetris => Some(include_bytes!("../../assets/audio/music_tetris.qoa")),
            Self::MusicPPAP | Self::MusicPen => {
                Some(include_bytes!("../../assets/audio/music_ppap.qoa"))
            }
            Self::MusicNyan => Some(include_bytes!("../../assets/audio/music_nyan_cat.qoa")),
            Self::CryTorchic => Some(include_bytes!("../../assets/audio/cry_torchic.qoa")),
            Self::CryEevee => Some(include_bytes!("../../assets/audio/cry_eevee.qoa")),
            Self::CryTreecko => Some(include_bytes!("../../assets/audio/cry_treecko.qoa")),
            _ => None,
        }
    }

    pub const fn into_audio_file(&self) -> Option<&'static [u8]> {
        self.file()
    }
}
