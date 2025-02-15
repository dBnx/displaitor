//! Displays an animated Nyan cat
#![no_std]
#![no_main]
#![feature(generic_const_exprs)]
#![allow(incomplete_features)]
#![allow(static_mut_refs)]

mod monitor;

use alloc::boxed::Box;
use cortex_m::interrupt::Mutex;
use defmt::{debug, info};
// use defmt::*;
use defmt_rtt as _;
use displaitor::App;
use embedded_alloc::LlffHeap as Heap;
#[allow(unused_imports)]
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
#[allow(unused_imports)]
use embedded_hal::digital::v2::{InputPin, OutputPin, ToggleableOutputPin};
use hub75_pio::{self, dma::DMAExt, lut::GammaLut};
use rp2040_hal::{gpio::PullNone, pio::PIOExt, Timer, multicore};

use panic_probe as _;

use bsp::entry;
use bsp::hal::{
    clocks::{init_clocks_and_plls, Clock},
    pac,
    sio::Sio,
    watchdog::Watchdog,
};
use rp_pico::{self as bsp};

extern crate alloc;

const COLOR_DEPTH: usize = 10;
static mut DISPLAY_BUFFER: hub75_pio::DisplayMemory<64, 32, COLOR_DEPTH> =
    hub75_pio::DisplayMemory::new();

#[entry]
fn main() -> ! {
    info!("Init heap ..");
    heap_init();

    info!("Init peripherals ..");
    let mut pac = pac::Peripherals::take().unwrap();
    let core = pac::CorePeripherals::take().unwrap();
    let mut watchdog = Watchdog::new(pac.WATCHDOG);
    let mut sio = Sio::new(pac.SIO);

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

    let pin_dpad_u = pins.gpio16.into_pull_up_input();
    let pin_dpad_d = pins.gpio17.into_pull_up_input();
    let pin_dpad_l = pins.b_power_save.into_pull_up_input();
    let pin_dpad_r = pins.gpio18.into_pull_up_input();
    let pin_button_a = pins.gpio14.into_pull_up_input();
    let pin_button_b = pins.gpio15.into_pull_up_input();
    let pin_button_s = pins.vbus_detect.into_pull_up_input();
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
    // let mut display = display.transformed(Transform::Rotate180);

    info!("Init splash screen & app ..");
    let mut app_splash_screen = displaitor::startup_app();
    let mut app = displaitor::main_app();

    // µs resolution
    let timer = Timer::new(pac.TIMER, &mut resets, &clocks);
    let mut time_last_us = 0;

    let mut monitor = monitor::Monitor::new();

    info!("Splash screen");
    while !app_splash_screen.close_request() {
        pin_led.set_high().unwrap(); // High ~ Update phase

        // Update time
        let time_current_us = timer.get_counter().ticks();
        let dt_us = time_current_us - time_last_us;
        time_last_us = time_current_us;

        // Read controls
        let controls = displaitor::Controls::new(
            pin_button_a.is_high().unwrap(),
            pin_button_b.is_high().unwrap(),
            pin_button_s.is_high().unwrap(),
            pin_dpad_u.is_high().unwrap(),
            pin_dpad_d.is_high().unwrap(),
            pin_dpad_l.is_high().unwrap(),
            pin_dpad_r.is_high().unwrap(),
        );

        // Update, Render & swap frame buffers
        app_splash_screen.update(dt_us as i64, time_current_us as i64, &controls);
        pin_led.set_low().unwrap(); // Low ~ Render & FB swap
        app_splash_screen.render(&mut display);
        display.commit();

        let _ = monitor.tick(time_current_us as u32);
    }

    info!("Initialize second core ..");
    static mut CORE1_STACK: multicore::Stack<4096> = multicore::Stack::new();
    let mut mc = multicore::Multicore::new(&mut pac.PSM, &mut pac.PPB, &mut sio.fifo);
    let cores = mc.cores();
    let core1 = &mut cores[1];
    let _test = core1.spawn(unsafe { &mut CORE1_STACK.mem }, core1_task);


    // let mut app = Mutex::new(app);
    info!("Start loop");
    loop {
        pin_led.set_high().unwrap(); // High ~ Update phase

        // Update time
        let time_current_us = timer.get_counter().ticks();
        let dt_us = time_current_us - time_last_us;
        time_last_us = time_current_us;

        // Read controls
        let controls = displaitor::Controls::new(
            pin_button_a.is_high().unwrap(),
            pin_button_b.is_high().unwrap(),
            pin_button_s.is_high().unwrap(),
            pin_dpad_u.is_high().unwrap(),
            pin_dpad_d.is_high().unwrap(),
            pin_dpad_l.is_high().unwrap(),
            pin_dpad_r.is_high().unwrap(),
        );

        // Update, Render & swap frame buffers
        app.update(dt_us as i64, time_current_us as i64, &controls);
        pin_led.set_low().unwrap(); // Low ~ Render & FB swap
        app.render(&mut display);
        display.commit();

        let _ = monitor.tick(time_current_us as u32);
    }
}

fn core1_task() -> () {
    loop {
        cortex_m::asm::wfi();
    }
}

#[global_allocator]
static HEAP: Heap = Heap::empty();

pub fn heap_init() {
    // Initialize the allocator BEFORE you use it
    use core::mem::MaybeUninit;
    const HEAP_SIZE_COL: usize = 3 * 2 * (1 << COLOR_DEPTH);
    const HEAP_SIZE_APP: usize = 8 * 1024;

    const HEAP_SIZE: usize = HEAP_SIZE_COL + HEAP_SIZE_APP;

    // #[link_section = ".heap"]
    static mut HEAP_MEM: [MaybeUninit<u8>; HEAP_SIZE] = [MaybeUninit::uninit(); HEAP_SIZE];
    unsafe { HEAP.init(&raw mut HEAP_MEM as usize, HEAP_SIZE) };
}
