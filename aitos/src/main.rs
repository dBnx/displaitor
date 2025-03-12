//! Displays an animated Nyan cat
#![no_std]
#![no_main]
#![feature(generic_const_exprs)]
#![allow(incomplete_features)]
#![allow(static_mut_refs)]

#![allow(unused_variables, unused_mut, unreachable_code, unused_assignments)] // RMME: Debugging

mod monitor;

use alloc::boxed::Box;
use core::mem::MaybeUninit;

#[allow(unused_imports)]
use defmt::{debug, error, info, warn};
// use defmt::*;
use defmt_rtt as _;
use displaitor::{App, AudioID};
use embedded_alloc::LlffHeap as Heap;
#[allow(unused_imports)]
use embedded_graphics::{pixelcolor::Rgb565, prelude::*};
#[allow(unused_imports)]
use embedded_hal::digital::v2::{InputPin, OutputPin, ToggleableOutputPin};
use embedded_hal::PwmPin;
use hub75_pio::{self, dma::DMAExt, lut::GammaLut};
use qoa_decoder::QoaDecoder;
use rp2040_hal::gpio::FunctionPwm;
use rp2040_hal::pwm;
use rp2040_hal::{gpio::PullNone, pio::PIOExt, Timer};
#[cfg(feature="audio")]
use rp2040_hal::multicore;

// use cortex_m::interrupt::Mutex;
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

// type AudioPwm = Pin<DynPinId, FunctionPwm, PullNone>;
// type AudioPwm = rp2040_hal::pwm::Channel<rp2040_hal::pwm::Slice<rp2040_hal::pwm::Pwm0, rp2040_hal::pwm::FreeRunning>, rp2040_hal::pwm::A>;
// type AudioPwm = rp2040_hal::pwm::Channel<>;
// static mut PWM_AUDIO_CHANNEL: Option<&'static mut AudioPwm> = None;
static mut AUDIO_ENABLE: bool = true;

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

    // --------------- PWM --------------------
    unsafe {
        // Write the PWM slices into the static. This makes them 'static.
        PWM_SLICES.write(pwm::Slices::new(pac.PWM, &mut resets));
        let pwm_slices = PWM_SLICES.assume_init_mut();

        // Select the PWM slice corresponding to your pin (for example, slice0).
        let pwm_slice = &mut pwm_slices.pwm5;
        pwm_slice.set_div_int(1);
        pwm_slice.set_div_frac(0);
        pwm_slice.set_top(255); // Affects frequency!
        pwm_slice.enable();

        warn!(
            "PWM: Max duty cycle: {}",
            pwm_slice.channel_b.get_max_duty()
        );

        // Store a reference to the channel in the global static.
        PWM_AUDIO_CHANNEL = Some(&mut pwm_slice.channel_b);
    }
    // Prepare pin
    // GPIO27 is connected to PWM channel 5B
    let mut _pin_audio_pwm = pins
        .gpio27
        .into_pull_type::<PullNone>()
        .into_function::<FunctionPwm>()
        .into_dyn_pin();

    // --------------- MISC --------------------
    // let mut pin_led = pins.gpio27.into_push_pull_output();
    let mut pin_led = pins.gpio28.into_push_pull_output();
    let mut pin_ce_led_pwr = pins.gpio22.into_push_pull_output();
    let mut pin_ce_lvl_shft = pins.gpio19.into_push_pull_output();
    let _pin_i2c_pdc_sda = pins.gpio20.into_floating_input();
    let _pin_i2c_pdc_scl = pins.gpio21.into_floating_input();
    fn calc_lut() -> GammaLut<COLOR_DEPTH, Rgb565, hub75_pio::lut::Init> {
        let lut = GammaLut::new();
        lut.init((1.0, 1.0, 1.0))
    }

    // --------------- Control --------------------
    let pin_dpad_u = pins.gpio16.into_pull_up_input();
    let pin_dpad_d = pins.gpio17.into_pull_up_input();
    let pin_dpad_l = pins.b_power_save.into_pull_up_input();
    let pin_dpad_r = pins.gpio18.into_pull_up_input();
    let pin_button_a = pins.gpio14.into_pull_up_input();
    let pin_button_b = pins.gpio15.into_pull_up_input();
    let pin_button_s = pins.voltage_monitor.into_pull_up_input();
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
    unsafe { 
        TIMER = Some(timer.clone());
    }

    let mut monitor = monitor::Monitor::new();

    #[cfg(feature="audio")]
    {
        info!("Initialize second core ..");
        static mut CORE1_STACK: multicore::Stack<6144> = multicore::Stack::new();
        let mut mc = multicore::Multicore::new(&mut pac.PSM, &mut pac.PPB, &mut sio.fifo);
        let cores = mc.cores();
        let core1 = &mut cores[1];
        let _test = core1.spawn(unsafe { &mut CORE1_STACK.mem }, core1_task);
    }

    audio_set(AudioID::MusicDepp);

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
        let update_result =
            app_splash_screen.update(dt_us as i64, time_current_us as i64, &controls);
        pin_led.set_low().unwrap(); // Low ~ Render & FB swap

        if update_result.visible_changes() {
            app_splash_screen.render(&mut display);
            display.commit();
        }

        let _ = monitor.tick(time_current_us as u32);
    }


    // let mut app = Mutex::new(app);
    // let app_copy = app.borrow(|app| app.clone());
    info!("Start loop");
    audio_reset();
    // run_app_to_completion();
    let mut button_s_history: u8 = 0;
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
        if controls.buttons_s {
            // info!("Button S    pressed!");
        }
        else {
            warn!("Button S de-pressed!");
        }
        button_s_history = (button_s_history << 1) | controls.buttons_s as u8;
        if button_s_history == 0b1111_0000 {
            let new = !unsafe{AUDIO_ENABLE};
            unsafe{AUDIO_ENABLE = !new};
            info!("Toggle audio: {}", new); 
        }

        // Update, Render & swap frame buffers
        let update_result = app.update(dt_us as i64, time_current_us as i64, &controls);

        // Update Sound Subsystem
        if let Some(audio_id) = update_result.audio_queue_request() {
            audio_set(audio_id);
        }

        // Update Display
        pin_led.set_low().unwrap(); // Low ~ Render & FB swap
        if update_result.visible_changes() {
            app.render(&mut display);
            display.commit();
        }

        let _ = monitor.tick(time_current_us as u32);
        cortex_m::asm::delay(400);
    }
}

fn run_app_to_completion() {
    todo!("TODO: PTR: Dies.");
}

fn audio_reset() {
    let _ = unsafe{AUDIO_ID.take()};
}

fn audio_set(audio_id: AudioID) {
    unsafe{AUDIO_ID = Some(audio_id)};
}


type AudioPwm = pwm::Channel<pwm::Slice<pwm::Pwm5, pwm::FreeRunning>, pwm::B>;
static mut PWM_SLICES: MaybeUninit<pwm::Slices> = MaybeUninit::uninit();
static mut PWM_AUDIO_CHANNEL: Option<&'static mut AudioPwm> = None;
static mut TIMER: Option<Timer> = None;
static mut AUDIO_ID: Option<AudioID> = None;

// fn init_pwm(pac: rp2040_hal::pac::Peripherals, resets: &mut rp2040_hal::pac::RESETS) {
// }

// mod qoa;
// pub use qoa::QoaDecoder;

#[cfg(feature="audio")]
fn core1_task() -> () {
    while unsafe { PWM_AUDIO_CHANNEL.is_none() || TIMER.is_none() } {
        cortex_m::asm::dmb();
    }

    let audio_pin = unsafe { PWM_AUDIO_CHANNEL.take().expect("PWM pin initialized") };
    let timer = unsafe { TIMER.take().expect("Timer initialized") };

    play_audio(audio_pin,  &timer);
    // loop {
    //     cortex_m::asm::wfi();
    // }
}

/// Converts a signed 16‑bit sample (range: –32768..32767) into a PWM duty cycle (0..max_duty).
fn sample_to_duty(sample: i16, max_duty: u16) -> u16 {
    (((sample as i32 + 32768) as u32 * (max_duty as u32)) / 65535) as u16
}

struct CurrentAudio {
    id: AudioID,
    audio: QoaDecoder<'static>,
    sample_rate: u32,
    sample_period_us: u32,
}

impl CurrentAudio {
    fn new(id: AudioID) -> Option<Self> {
        let audio = QoaDecoder::new(id.into_audio_file()?).expect("QOA is valid");
        let sample_rate = audio.sample_rate();
        let sample_period_us = (1_000_000 / sample_rate) as u32;
        Some(CurrentAudio {
            id,
            audio,
            sample_rate,
            sample_period_us,
        })
    }

    fn print(&self) {
        info!(
            "Playing Audio ID {:?} Sample Rate: {} | Sample Period : {}us",
            self.id,
            self.sample_rate,
            self.sample_period_us
        );
    }
}

/// Plays the embedded QOA file on the provided PWM pin. This function never returns.
/// It uses the cortex‑m asm delay (assuming a 125 MHz clock) to wait for the sample period.
pub fn play_audio<P>(pwm: &mut P, timer: &Timer) -> !
where
    P: PwmPin<Duty = u16>,
{
    // Calculate delay in microseconds per sample.
    const CYCLES_PER_US: u32 = 125; // assuming a 125 MHz clock

    let mut current_audio = None;
    let mut time_last_us = timer.get_counter().ticks();
    let mut sample_count = 0;
    let mut last_audio_id = None;
    loop {

        // Update audio queue request
        let mut reset_audio = false;
        if let Some(audio) = unsafe {AUDIO_ID.take()} {
            match &last_audio_id {
                Some(last_audio) if &audio == last_audio => {
                    reset_audio = true;
                }
                // If we are not playing anything, or something different
                _ if unsafe{AUDIO_ENABLE} == true => {
                    last_audio_id = Some(audio);

                    current_audio = CurrentAudio::new(audio);
                    if let Some( audio) = &current_audio {
                        audio.print();
                    }
                    else 
                    {
                        info!("Stopping audio");
                    }
                }
                _ => { }
            }
        }

        // Wait for next audio
        if current_audio.is_none() {
            cortex_m::asm::delay(200);
            continue;
        }

        let mut reset = false;
        {
            let current_audio = current_audio.as_mut().unwrap();

            let time_current_us = timer.get_counter().ticks();

            if let Some(samples) = current_audio.audio.next_sample() {
                let sample = samples; // [1];

                let duty = sample_to_duty(sample, pwm.get_max_duty());
                pwm.set_duty(duty);
                // Delay for one sample period.
                let decoding_time = time_current_us.saturating_sub(time_last_us) as u32; // TODO: Make it more robust
                if decoding_time > current_audio.sample_period_us {
                    time_last_us = time_current_us;
                    continue;
                }

                let sleep_time =current_audio. sample_period_us.saturating_sub(decoding_time);
                cortex_m::asm::delay(sleep_time * CYCLES_PER_US);
                sample_count += 1;
                if sample_count == 20_000 {
                    info!("#samples: {} | sample period {}µs | decoding time {}µs | sleep for {}µs", sample_count, current_audio.sample_period_us, decoding_time, sleep_time);
                    sample_count = 0;
                }
                time_last_us = time_current_us;
            } else {
                warn!("EOF - Reseting audio!");
                // current_audio.audio.reset();
                reset = true;
            }
        }
        if reset {
            current_audio = None;
            last_audio_id = None;
        }

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

// #[cfg(not(test))]
// #[panic_handler]
// fn panic(info: &core::panic::PanicInfo) -> ! {
//     defmt::error!("PANIC: {}", info);
//     cortex_m::asm::bkpt();
//     loop {}
// } 

// #[cfg(not(test))]
// #[panic_handler]
// fn panic(_info: &core::panic::PanicInfo) -> ! {
//     loop {}
// }

#[defmt::panic_handler]
fn panic() -> ! {
    cortex_m::asm::bkpt();
    loop {}
}