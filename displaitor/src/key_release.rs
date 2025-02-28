#[derive(Default, Clone, PartialEq, Debug)]
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
