/// Logical controls: `true` always means pressed, regardless of GPIO polarity.
/// Hardware adapters must debounce buttons before passing them to the engine.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Controls {
    pub buttons_a: bool,
    pub buttons_b: bool,
    pub buttons_s: bool,
    pub dpad_up: bool,
    pub dpad_down: bool,
    pub dpad_left: bool,
    pub dpad_right: bool,
}

impl Controls {
    pub(crate) fn rising(self, previous: Self) -> Self {
        Self {
            buttons_a: self.buttons_a && !previous.buttons_a,
            buttons_b: self.buttons_b && !previous.buttons_b,
            buttons_s: self.buttons_s && !previous.buttons_s,
            dpad_up: self.dpad_up && !previous.dpad_up,
            dpad_down: self.dpad_down && !previous.dpad_down,
            dpad_left: self.dpad_left && !previous.dpad_left,
            dpad_right: self.dpad_right && !previous.dpad_right,
        }
    }
}
