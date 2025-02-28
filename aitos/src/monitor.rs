use defmt::debug;

#[derive(Default, Debug)]
pub struct Monitor {
    last_update: u32,
    frames_rendered: u32,
}

impl Monitor {
    pub fn new() -> Monitor {
        Default::default()
    }

    /// Call after every frame rendered
    pub fn tick(&mut self, t_us: u32) -> Option<u32> {
        self.frames_rendered += 1;

        let dt_us = t_us.saturating_sub(self.last_update);

        const FRAMES_RENDERED_MIN: u32 = 60;
        const TIME_PASSED_MIN_MS: u32 = 3_000;
        if self.frames_rendered < FRAMES_RENDERED_MIN || dt_us < TIME_PASSED_MIN_MS * 1000 {
            return None;
        }

        let dt_ms = dt_us / 1000;
        let fps = self.frames_rendered * 1000 / dt_ms.max(1);

        debug!(
            "FPS: {:03}Hz | dt {:04}ms | frames: {:03}",
            fps, dt_ms, self.frames_rendered
        );

        self.frames_rendered = 0;
        self.last_update = t_us;
        Some(fps)
    }
}
