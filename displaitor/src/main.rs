use displaytor::{App, Controls};
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
use embedded_graphics_simulator::{
    sdl2::Keycode, OutputSettingsBuilder, SimulatorDisplay, SimulatorEvent, Window
};
use std::{thread::sleep, time::{Duration, Instant}};

const SCREEN_HEIGHT: u32 = 32;
const SCREEN_WIDTH: u32 = 64;

fn main() -> Result<(), core::convert::Infallible> {
    // let mut app = displaytor::games::Pong::new(SCREEN_WIDTH, SCREEN_HEIGHT);
    // let mut app: displaytor::games::Snake<SCREEN_WIDTH, SCREEN_HEIGHT, 32> = displaytor::games::Snake::new();
    let mut app = displaytor::main_app();
    run_app(&mut app);
    Ok(())
}

pub fn run_app<T>(app: &mut T) 
where
    T: App<Target = SimulatorDisplay<Rgb565>, Color = Rgb565>
{
    // Create a simulated display with a resolution of 240x240 pixels
    let mut display = SimulatorDisplay::<Rgb565>::new(Size::new(SCREEN_WIDTH, SCREEN_HEIGHT));

    // Create a window for rendering the display
    let output_settings = OutputSettingsBuilder::new()
        // .theme(BinaryColorTheme::OledBlue)
        .scale(4)
        .pixel_spacing(4)
        .build();

    let mut window = Window::new("Displaytor Simulator", &output_settings);

    // Timer for controlling the game loop
    // let mut timer = SimulatorTimer::new(Duration::from_millis(16)); // ~60 FPS

    // Initialize the app
    // app.setup();

    // Game loop
    let mut last_time = Instant::now();
    let mut elapsed_time = 0; // Elapsed time in milliseconds
    let mut controls = Controls {
        buttons_a: false,
        buttons_b: false,
        dpad_up: false,
        dpad_down: false,
        dpad_left: false,
        dpad_right: false,
    };

    'game_loop: loop {
        // Calculate elapsed time
        let now = Instant::now();
        let dt = now.duration_since(last_time).as_millis() as i64;
        elapsed_time += dt;
        last_time = now;

        // Update the app
        app.update(dt, elapsed_time, &controls);

        // Clear the display
        display.clear(Rgb565::BLACK).unwrap();

        // Render the app
        app.render(&mut display);

        // Update the window
        window.update(&display);

        // Handle events
        for event in window.events() {
            match event {
                SimulatorEvent::Quit => break 'game_loop,
                SimulatorEvent::KeyUp { keycode, .. } => match keycode {
                    Keycode::W => controls.dpad_up = false,
                    Keycode::S => controls.dpad_down = false,
                    Keycode::A => controls.dpad_left = false,
                    Keycode::D => controls.dpad_right = false,
                    Keycode::Space => controls.buttons_a = false,
                    Keycode::Q => controls.buttons_b = false,
                    _ => {}
                },
                SimulatorEvent::KeyDown { keycode, .. } => match keycode {
                    Keycode::W => controls.dpad_up = true,
                    Keycode::S => controls.dpad_down = true,
                    Keycode::A => controls.dpad_left = true,
                    Keycode::D => controls.dpad_right = true,
                    Keycode::Space => controls.buttons_a = true,
                    Keycode::Q => controls.buttons_b = true,
                    _ => {}
                },
                _ => {}
            }
        }

        // Wait for the next frame
        // timer.wait();
        sleep(Duration::from_millis(15));
    }

    // Cleanup
    app.teardown();
}
