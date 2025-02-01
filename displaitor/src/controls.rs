// TODO: init with pins and then provide .update()
pub struct Controls {
    pub buttons_a: bool,
    pub buttons_b: bool,
    pub dpad_up: bool,
    pub dpad_down: bool,
    pub dpad_left: bool,
    pub dpad_right: bool,
}


impl Controls {
    pub fn new(
        buttons_a: bool,
        buttons_b: bool,
        dpad_up: bool,
        dpad_down: bool,
        dpad_left: bool,
        dpad_right: bool,
    ) -> Controls {
        Controls {
            buttons_a,
            buttons_b,
            dpad_up,
            dpad_down,
            dpad_left,
            dpad_right,
        }
    }
}