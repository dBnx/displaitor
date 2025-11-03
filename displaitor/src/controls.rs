// TODO: init with pins and then provide .update()
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
    pub fn new(
        buttons_a: bool,
        buttons_b: bool,
        buttons_s: bool,
        dpad_up: bool,
        dpad_down: bool,
        dpad_left: bool,
        dpad_right: bool,
    ) -> Controls {
        Controls {
            buttons_a,
            buttons_b,
            buttons_s,
            dpad_up,
            dpad_down,
            dpad_left,
            dpad_right,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_initializes_all_fields() {
        let controls = Controls::new(
            true, false, true,
            false, true, false, true,
        );
        assert!(controls.buttons_a);
        assert!(!controls.buttons_b);
        assert!(controls.buttons_s);
        assert!(!controls.dpad_up);
        assert!(controls.dpad_down);
        assert!(!controls.dpad_left);
        assert!(controls.dpad_right);
    }

    #[test]
    fn test_new_all_false() {
        let controls = Controls::new(
            false, false, false,
            false, false, false, false,
        );
        assert!(!controls.buttons_a);
        assert!(!controls.buttons_b);
        assert!(!controls.buttons_s);
        assert!(!controls.dpad_up);
        assert!(!controls.dpad_down);
        assert!(!controls.dpad_left);
        assert!(!controls.dpad_right);
    }

    #[test]
    fn test_new_all_true() {
        let controls = Controls::new(
            true, true, true,
            true, true, true, true,
        );
        assert!(controls.buttons_a);
        assert!(controls.buttons_b);
        assert!(controls.buttons_s);
        assert!(controls.dpad_up);
        assert!(controls.dpad_down);
        assert!(controls.dpad_left);
        assert!(controls.dpad_right);
    }
}
