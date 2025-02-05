//! Displays an animated Nyan cat
#![no_std]
#![no_main]
#![feature(generic_const_exprs)]
#![allow(incomplete_features)]
#![allow(static_mut_refs)]

use alloc::boxed::Box;
use defmt::info;
// use defmt::*;
use defmt_rtt as _;
use displaitor::App;
use embedded_alloc::LlffHeap as Heap;
use embedded_graphics::pixelcolor::Rgb565;
use embedded_hal::digital::v2::{InputPin, OutputPin, ToggleableOutputPin};
use hub75_pio::dma::DMAExt;
use hub75_pio::lut::GammaLut;
use hub75_pio::{self};
use rp2040_hal::{gpio::PullNone, pio::PIOExt, Timer};

use panic_probe as _;

use rp_pico::{self as bsp};
use bsp::entry;
use bsp::hal::{
    clocks::{init_clocks_and_plls, Clock},
    pac,
    sio::Sio,
    watchdog::Watchdog,
};

extern crate alloc;

const COLOR_DEPTH: usize = 10;
static mut DISPLAY_BUFFER: hub75_pio::DisplayMemory<64, 32, COLOR_DEPTH> = hub75_pio::DisplayMemory::new();

#[entry]
fn main() -> ! {
    info!("Program start");
    info!("Init heap ..");
    heap_init();

    info!("Init peripherals ..");
    let mut pac = pac::Peripherals::take().unwrap();
    let core = pac::CorePeripherals::take().unwrap();
    let mut watchdog = Watchdog::new(pac.WATCHDOG);
    let sio = Sio::new(pac.SIO);

    // External high-speed crystal on the pico board is 12Mhz
    let external_xtal_freq_hz = 12_000_000u32;
    let clocks = init_clocks_and_plls(
        external_xtal_freq_hz,
        pac.XOSC,
        pac.CLOCKS,
        pac.PLL_SYS,
        pac.PLL_USB,
        &mut pac.RESETS,
        &mut watchdog,
    )
    .ok()
    .unwrap();

    #[allow(unused_variables, unused_mut)]
    let mut delay = cortex_m::delay::Delay::new(core.SYST, clocks.system_clock.freq().to_Hz());

    let pins = bsp::Pins::new(
        pac.IO_BANK0,
        pac.PADS_BANK0,
        sio.gpio_bank0,
        &mut pac.RESETS,
    );

    // Split PIO0 SM
    let (mut pio, sm0, sm1, sm2, _) = pac.PIO0.split(&mut pac.RESETS);

    // Reset DMA
    let mut resets = pac.RESETS;
    resets.reset.modify(|_, w| w.dma().set_bit());
    resets.reset.modify(|_, w| w.dma().clear_bit());
    while resets.reset_done.read().dma().bit_is_clear() {}

    // Split DMA
    let dma = pac.DMA.split();

    let hub75_pins = hub75_pio::DisplayPins {
        r1: pins
            .gpio0
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        g1: pins
            .gpio1
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        b1: pins
            .gpio2
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        r2: pins
            .gpio3
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        g2: pins
            .gpio4
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        b2: pins
            .gpio5
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        addra: pins
            .gpio6
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        addrb: pins
            .gpio7
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        addrc: pins
            .gpio8
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        addrd: pins
            .gpio9
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        clk: pins
            .gpio11
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        lat: pins
            .gpio12
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
        oe: pins
            .gpio13
            .into_function()
            .into_pull_type::<PullNone>()
            .into_dyn_pin(),
    };
    let mut pin_hub75_addre = pins.gpio10.into_push_pull_output();
    let _ = pin_hub75_addre.set_low();

    /*
    let mut pin_led = pins.led.into_push_pull_output();
    let pin_dpad_u = pins.gpio22.into_pull_up_input();
    let pin_dpad_d = pins.gpio21.into_pull_up_input();
    let pin_dpad_l = pins.gpio20.into_pull_up_input();
    let pin_dpad_r = pins.gpio19.into_pull_up_input();
    let pin_button_a = pins.gpio18.into_pull_up_input();
    let pin_button_b = pins.gpio17.into_pull_up_input();
    let _pin_button_s = pins.gpio16.into_pull_up_input();
    */
    let mut pin_led = pins.gpio27.into_push_pull_output();
    let mut pin_ce_led_pwr = pins.gpio22.into_push_pull_output();
    let mut pin_ce_lvl_shft = pins.gpio19.into_push_pull_output();
    let _pin_i2c_pdc_sda = pins.gpio20.into_floating_input();
    let _pin_i2c_pdc_scl = pins.gpio21.into_floating_input();
    fn calc_lut() -> GammaLut<COLOR_DEPTH, Rgb565, hub75_pio::lut::Init> {
        let lut = GammaLut::new();
        lut.init((1.0, 1.0, 1.0))
    }


    let pin_dpad_u = pins.b_power_save.into_pull_up_input();
    let pin_dpad_d = pins.gpio18.into_pull_up_input();
    let pin_dpad_l = pins.gpio17.into_pull_up_input();
    let pin_dpad_r = pins.gpio16.into_pull_up_input();
    let pin_button_a = pins.gpio14.into_pull_up_input();
    let pin_button_b = pins.gpio15.into_pull_up_input();
    // let _pin_button_s = pins.gpio24.into_pull_up_input();
    pin_ce_led_pwr.set_high().unwrap();
    pin_ce_lvl_shft.set_low().unwrap();


    let lut = Box::new(calc_lut());
    let lut = Box::leak(lut);
    let benchmark = true;
    let mut display = unsafe {
        hub75_pio::Display::new(
            &mut DISPLAY_BUFFER,
            hub75_pins,
            &mut pio,
            (sm0, sm1, sm2),
            (dma.ch0, dma.ch1, dma.ch2, dma.ch3),
            benchmark,
            lut,
        )
    };


    let mut app = displaitor::main_app();

    let timer = Timer::new(pac.TIMER, &mut resets, &clocks);
    let mut time_last = 0;
    pin_led.set_high().unwrap();
    loop {
        // Update time
        // TODO: Ticks to µs conversion
        let time_current = timer.get_counter().ticks();
        let dt = time_current - time_last;
        time_last = time_current;

        // Read controls
        let controls = displaitor::Controls::new(
            pin_button_a.is_high().unwrap(),
            pin_button_b.is_high().unwrap(),
            // pin_button_s.read(),
            pin_dpad_u.is_high().unwrap(),
            pin_dpad_d.is_high().unwrap(),
            pin_dpad_l.is_high().unwrap(),
            pin_dpad_r.is_high().unwrap(),
        );

        // Update, Render & swap frame buffers
        app.update(dt as i64, time_current as i64, &controls);
        app.render(&mut display);
        display.commit();

        // delay.delay_ms(1000);
        // println!("Dummy loop");
        pin_led.toggle().unwrap();
    }
}

/*
#![no_std]
#![no_main]
#![allow(unused_imports)]

use bsp::entry;
use defmt::*;
use defmt_rtt as _;
use embedded_hal::digital::InputPin;
use panic_probe as _;

// Provide an alias for our BSP so we can switch targets quickly.
// Uncomment the BSP you included in Cargo.toml, the rest of the code does not need to change.
use rp_pico as bsp;

use bsp::hal::{
    self,
    clocks::{init_clocks_and_plls, Clock},
    pac,
    sio::Sio,
    watchdog::Watchdog,
};

use embedded_graphics::{
    prelude::*,
};
// Font6x8
// Style


mod lib {
    use embedded_graphics::{
        mono_font::{ascii::FONT_6X9, MonoTextStyle}, pixelcolor::Rgb565, prelude::*, primitives::{Rectangle, StyledDrawable}, text::Text
    };

    static IMAGE: &'static [u8] = include_bytes!("../../Ferd.qoi");

    pub struct Controls {
        buttons_a: bool,
        buttons_b: bool,
        dpad_up: bool,
        dpad_down: bool,
        dpad_left: bool,
        dpad_right: bool,
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

    pub struct State<'a> {
        qoi: tinyqoi::Qoi<'a>,
        time: u32,
    }

    impl<'a> State<'a> {
        pub fn new() -> State<'a> {
            let qoi = tinyqoi::Qoi::new(IMAGE).unwrap();

            State {
                qoi: qoi,
                time: 0,
            }
        }

        pub fn update(&mut self, controls: &Controls, time: u32, dt: u32) -> () {
            // info!("Updating state");
            let _ = controls;
            let _ = dt;

            self.time = time;
        }

        pub fn draw<D>(&mut self, target: &mut D) -> ()
        where
            D: DrawTarget<Color = Rgb565>,
        {
            let slow_time = self.time >> 16;

            // Draw
            Rectangle::new(Point::new(10, 20), Size::new(20, 30))
                .into_styled(Rgb565::GREEN)
                .draw(target).unwrap();


            Rectangle::new(Point::new(30, 20), Size::new(50, 30))
                .into_styled(Rgb565::WHITE)
                .draw(target).unwrap();

            let color = cycle_color(slow_time as i8, 255, 255);
            let style = MonoTextStyle::new(&FONT_6X9, color);
            // Create a text at position (20, 30) and draw it using the previously defined style
            Text::new("Hello Rust!", Point::new(1, 1), style)
                .draw(target);

            // FONT_6X9
            // font.stroke_color = Some(Rgb565::from(color));
            // let text = Font6x8::render_str("Displaitor").style(font);
            // display.draw(text);

            // use embedded_graphics_core::geometry::OriginDimensions;
            // use embedded_
            // let size = self.qoi.size();
            // display.draw(&self.qoi);
            /*
            let width = self.qoi.pixels().
            display.draw(self.qoi.pixels().map(
                |p| -> Pixel<Rgb565> {
                    let pos_x = 0;
                    let pos_y = 0;
                    let color = p.into(); // Rgb565::from((p.r, p.g, p.b)).into()
                    Pixel(
                        UnsignedCoord::new(pos_x, pos_y), color
                    )
                }
            ));
            */
        }
    }

    fn cycle_color(value: i8, saturation: u8, v: u8) -> Rgb565 {
        // Normalize the value to a range between 0 and 255
        let norm_value = (value as u8).wrapping_add(128);

        // Map the normalized value to a hue range of 0-360
        let hue = (norm_value as u16) * 360 / 256;

        let (r, g, b) = hsv_to_rgb(hue, saturation, v); // Full saturation and brightness

        Rgb565::new(r, g, b)
    }

    fn hsv_to_rgb(h: u16, s: u8, v: u8) -> (u8, u8, u8) {
        let c = (v as u16 * s as u16) / 255;
        let x = (c * (60 - (h % 120) as u16) / 60) as u8;
        let m = (v as u16 - c) as u8;

        let (r, g, b) = match h / 60 {
            0 => (c as u8, x, 0),
            1 => (x, c as u8, 0),
            2 => (0, c as u8, x),
            3 => (0, x, c as u8),
            4 => (x, 0, c as u8),
            _ => (c as u8, 0, x),
        };

        (r + m, g + m, b + m)
    }

}

#[entry]
fn main() -> ! {
    info!("Program start");
    let mut pac = pac::Peripherals::take().unwrap();
    let core = pac::CorePeripherals::take().unwrap();
    let mut watchdog = Watchdog::new(pac.WATCHDOG);
    let sio = Sio::new(pac.SIO);

    // External high-speed crystal on the pico board is 12Mhz
    let external_xtal_freq_hz = 12_000_000u32;
    let clocks = init_clocks_and_plls(
        external_xtal_freq_hz,
        pac.XOSC,
        pac.CLOCKS,
        pac.PLL_SYS,
        pac.PLL_USB,
        &mut pac.RESETS,
        &mut watchdog,
    )
    .ok()
    .unwrap();

    let mut delay = cortex_m::delay::Delay::new(core.SYST, clocks.system_clock.freq().to_Hz());

    let pins = bsp::Pins::new(
        pac.IO_BANK0,
        pac.PADS_BANK0,
        sio.gpio_bank0,
        &mut pac.RESETS,
    );

    // This is the correct pin on the Raspberry Pico board. On other boards, even if they have an
    // on-board LED, it might need to be changed.
    //
    // Notably, on the Pico W, the LED is not connected to any of the RP2040 GPIOs but to the cyw43 module instead.
    // One way to do that is by using [embassy](https://github.com/embassy-rs/embassy/blob/main/examples/rp/src/bin/wifi_blinky.rs)
    //
    // If you have a Pico W and want to toggle a LED with a simple GPIO output pin, you can connect an external
    // LED to one of the GPIO pins, and reference that pin here. Don't forget adding an appropriate resistor
    // in series with the LED.
    let mut led_pin = pins.led.into_push_pull_output();

    // PINS HUB75
    let r1 = pins.gpio0.into_push_pull_output().into_dyn_pin(); // .into_function().into_pull_type().into_dyn_pin(); // .into_function().into_pull_type().into_dyn_pin();
    let g1 = pins.gpio1.into_push_pull_output().into_dyn_pin();
    let b1 = pins.gpio2.into_push_pull_output().into_dyn_pin();
    let r2 = pins.gpio3.into_push_pull_output().into_dyn_pin();
    let g2 = pins.gpio4.into_push_pull_output().into_dyn_pin();
    let b2 = pins.gpio5.into_push_pull_output().into_dyn_pin();
    let addra = pins.gpio6.into_push_pull_output().into_dyn_pin();
    let addrb = pins.gpio7.into_push_pull_output().into_dyn_pin();
    let addrc = pins.gpio8.into_push_pull_output().into_dyn_pin();
    let addrd = pins.gpio9.into_push_pull_output().into_dyn_pin();
    let clk = pins.gpio11.into_push_pull_output().into_dyn_pin();
    let lat = pins.gpio12.into_push_pull_output().into_dyn_pin();
    let oe = pins.gpio13.into_push_pull_output().into_dyn_pin();

    // PINS Control
    let mut buttons_a = pins.gpio14.as_input();
    let mut buttons_b = pins.gpio15.as_input();
    let mut dpad_up = pins.gpio16.as_input();
    let mut dpad_down = pins.gpio17.as_input();
    let mut dpad_left = pins.gpio18.as_input();
    let mut dpad_right = pins.gpio19.as_input();
    // TODO: Should be GPIO23, not GPIO19 ..

    // HUB75 Display
    let hub75_pins = (
        r1, g1, b1, r2, g2, b2, addra, addrb, addrc, addrd, clk, lat, oe,
    );

    let hub75_color_bits = 4;
    let mut display = hub75::Hub75::new(hub75_pins, hub75_color_bits);

    // State
    let timer = hal::Timer::new(pac.TIMER, &mut pac.RESETS, &clocks);
    let mut time_last = 0u32;
    let mut dt = 0u32;

    let mut state = lib::State::new();
    loop {
        // TODO: Use 64b?
        let time_current = timer.get_counter().ticks() as u32;
        dt = time_current - time_last;
        time_last = time_current;

        let controls = lib::Controls::new(
            buttons_a.is_high().unwrap(),
            buttons_b.is_high().unwrap(),
            dpad_up.is_high().unwrap(),
            dpad_down.is_high().unwrap(),
            dpad_left.is_high().unwrap(),
            dpad_right.is_high().unwrap(),
        );

        state.update(&controls, time_current, dt);

        for _ in 0..4 {
            state.draw(&mut display);
            display.output(&mut delay);
        }
    }
}
*/

#[global_allocator]
static HEAP: Heap = Heap::empty();

pub fn heap_init() {
    // Initialize the allocator BEFORE you use it
    use core::mem::MaybeUninit;
    const HEAP_SIZE_COL: usize = 3 * 2 * (1 << COLOR_DEPTH);
    const HEAP_SIZE_APP: usize = 4 * 1024;
    
    const HEAP_SIZE: usize = HEAP_SIZE_COL + HEAP_SIZE_APP;

    // #[link_section = ".heap"]
    static mut HEAP_MEM: [MaybeUninit<u8>; HEAP_SIZE] = [MaybeUninit::uninit(); HEAP_SIZE];
    unsafe { HEAP.init(&raw mut HEAP_MEM as usize, HEAP_SIZE) };
}
