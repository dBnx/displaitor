use defmt::info;

#[derive(Default, Clone, PartialEq, Debug, defmt::Format)]
enum States {
    #[default]
    KeyUnknown,
    KeyDown,
    KeyUp,
    KeyReleased,
}

#[derive(Default, Clone, PartialEq, Debug)]
pub struct KeyReleaseEvent {
    state: States,
    fired: bool,
}

impl KeyReleaseEvent {
    pub fn new() -> Self {
        Default::default()
    }

    pub fn reset(&mut self) {
        self.state = Default::default();
        self.fired = false;
    }

    pub fn update(&mut self, current_state: bool) {
        match self.state {
            // Only transition from unknown to down, if the current key is actually down. Otherwise we
            // couldn't detect a real press when starting a new app.
            States::KeyUnknown if current_state == false => self.state = States::KeyDown,
            States::KeyUnknown if current_state == true => self.state = States::KeyUp,
            States::KeyDown if current_state == true => self.state = States::KeyUp,
            States::KeyUp if current_state == false => self.state = States::KeyReleased,
            States::KeyReleased if current_state == false => self.state = States::KeyDown,
            States::KeyReleased if current_state == true => self.state = States::KeyUnknown,
            _ => {}
        }
    }

    pub fn fired(&self) -> bool {
        self.state == States::KeyReleased
        // self.fired
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_initializes_correctly() {
        let event = KeyReleaseEvent::new();
        assert!(!event.fired());
    }

    #[test]
    fn test_state_transition_unknown_to_down() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        assert!(!event.fired());
    }

    #[test]
    fn test_state_transition_unknown_to_up() {
        let mut event = KeyReleaseEvent::new();
        event.update(true);
        assert!(!event.fired());
    }

    #[test]
    fn test_state_transition_down_to_up() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        event.update(true);
        assert!(!event.fired());
    }

    #[test]
    fn test_state_transition_up_to_released() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        event.update(true);
        event.update(false);
        assert!(event.fired());
    }

    #[test]
    fn test_state_transition_complete_cycle() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        event.update(true);
        event.update(false);
        assert!(event.fired());
        event.update(false);
        assert!(!event.fired());
    }

    #[test]
    fn test_state_transition_released_to_unknown() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        event.update(true);
        event.update(false);
        assert!(event.fired());
        event.update(true);
        assert!(!event.fired());
    }

    #[test]
    fn test_reset() {
        let mut event = KeyReleaseEvent::new();
        event.update(false);
        event.update(true);
        event.update(false);
        assert!(event.fired());
        event.reset();
        assert!(!event.fired());
    }

    #[test]
    fn test_rapid_transitions() {
        let mut event = KeyReleaseEvent::new();
        event.update(true);
        event.update(false);
        assert!(event.fired());
        event.update(true);
        event.update(false);
        assert!(!event.fired());
    }
}
