use aitos::{display::PanelTarget, runtime::Runtime};
use core::future::pending;
use defmt_rtt as _;
use displaitor::{AppId, Engine, Screen};
use embassy_executor::Spawner;
use embassy_futures::select::select4;
use embassy_rp::{
    Peri, bind_interrupts,
    executor::{Executor, InterruptExecutor},
    gpio::{Input, Level, Output, Pull},
    interrupt::{InterruptExt, Priority},
    multicore::{Stack, spawn_core1},
    peripherals::{PIO0, USB},
    pio::Pio,
    pwm::{Config as PwmConfig, Pwm},
};
use embassy_time::{Instant, Timer};
use panic_probe as _;
use rp_hub75::{
    Hub75, Hub75Config, Hub75Pins16, Hub75Swap, framebuffer::bitplane::plain::DmaFrameBuffer,
    hub75_descriptors,
};
use static_cell::{ConstStaticCell, StaticCell};

// Six bitplanes preserve every distinct RGB565 intensity.
type Framebuffer = DmaFrameBuffer<16, 64, 6>;
static FB0: ConstStaticCell<Framebuffer> = ConstStaticCell::new(Framebuffer::new());
static FB1: ConstStaticCell<Framebuffer> = ConstStaticCell::new(Framebuffer::new());
static CORE1_STACK: ConstStaticCell<Stack<8192>> = ConstStaticCell::new(Stack::new());
static CORE1_EXECUTOR: StaticCell<Executor> = StaticCell::new();
static HIGH_EXECUTOR: InterruptExecutor = InterruptExecutor::new();

bind_interrupts!(struct Irqs {
    PIO0_IRQ_0 => embassy_rp::pio::InterruptHandler<PIO0>;
    USBCTRL_IRQ => embassy_rp::usb::InterruptHandler<USB>;
});
#[unsafe(no_mangle)]
extern "C" fn DMA_IRQ_1() {
    rp_hub75::on_dma_irq();
}
#[unsafe(no_mangle)]
unsafe extern "C" fn SWI_IRQ_0() {
    // Only core 0 starts this executor on SWI_IRQ_0.
    unsafe {
        HIGH_EXECUTOR.on_interrupt();
    }
}
#[embassy_executor::task]
async fn usb_task(usb: Peri<'static, USB>) {
    super::usb_canvas::run(usb, Irqs).await;
}

#[embassy_executor::main(
    executor = "embassy_rp::executor::Executor",
    entry = "cortex_m_rt::entry"
)]
async fn main(_spawner: Spawner) {
    let p = embassy_rp::init(Default::default());
    let system_clock_hz = embassy_rp::clocks::clk_sys_freq();
    // Input/USB work preempts rendering. Timer IRQ only wakes the priority task.
    embassy_rp::interrupt::TIMER_IRQ_0.set_priority(Priority::P0);
    embassy_rp::interrupt::USBCTRL_IRQ.set_priority(Priority::P0);
    embassy_rp::interrupt::SWI_IRQ_0.set_priority(Priority::P1);
    let high = HIGH_EXECUTOR.start(embassy_rp::interrupt::SWI_IRQ_0);
    let mut power = Output::new(p.PIN_22, Level::Low);
    let mut level_enable = Output::new(p.PIN_19, Level::High);
    let mut activity = Output::new(p.PIN_28, Level::Low);
    let _reserved_sda = Input::new(p.PIN_20, Pull::None);
    let _reserved_scl = Input::new(p.PIN_21, Pull::None);
    let input_started = super::buttons::init();
    high.spawn(
        super::buttons::run(
            super::buttons::Pins {
                a: Input::new(p.PIN_14, Pull::Up),
                b: Input::new(p.PIN_15, Pull::Up),
                select: Input::new(p.PIN_29, Pull::Up),
                up: Input::new(p.PIN_16, Pull::Up),
                down: Input::new(p.PIN_17, Pull::Up),
                // Physical directions confirmed on the original board.
                left: Input::new(p.PIN_18, Pull::Up),
                right: Input::new(p.PIN_23, Pull::Up),
            },
            input_started,
        )
        .unwrap(),
    );
    high.spawn(usb_task(p.USB).unwrap());

    let mut pio = Pio::new(p.PIO0, Irqs);
    let panel_pins = Hub75Pins16::new(
        &mut pio, p.PIN_0, p.PIN_1, p.PIN_2, p.PIN_3, p.PIN_4, p.PIN_5, p.PIN_6, p.PIN_7, p.PIN_8,
        p.PIN_9, p.PIN_10, p.PIN_12, p.PIN_13, p.PIN_11,
    );
    let hub75 = Hub75::new(
        pio,
        p.DMA_CH0,
        p.DMA_CH1,
        panel_pins,
        system_clock_hz,
        Hub75Config::new(embassy_rp::pac::Interrupt::DMA_IRQ_1),
        FB0.take(),
        hub75_descriptors!(Framebuffer),
    )
    .expect("start HUB75 DMA");
    let mut frame = Some(FB1.take());
    let mut pending_swap: Option<Hub75Swap<Framebuffer>> = None;
    let mut redraw = true;
    power.set_high();
    level_enable.set_low();
    defmt::info!(
        "HUB75 clock {} Hz, refresh {} Hz",
        hub75.panel_clock_hz(),
        hub75.refresh_hz()
    );

    let mut pwm_config = PwmConfig::default();
    pwm_config.divider = 1.into();
    pwm_config.top = 255;
    pwm_config.compare_b = 127;
    let pwm = Pwm::new_output_b(p.PWM_SLICE5, p.PIN_27, pwm_config);
    spawn_core1(p.CORE1, CORE1_STACK.take(), move || {
        CORE1_EXECUTOR.init(Executor::new()).run(|spawner| {
            spawner.spawn(
                super::audio_worker::run(pwm, (p.DMA_CH2, p.DMA_CH3, p.DMA_CH4), system_clock_hz)
                    .unwrap(),
            );
        });
    });

    let mut engine = Engine::new();
    let mut usb = super::usb_canvas::UsbCanvas::new();
    let mut runtime = Runtime::new(input_started);
    #[cfg(feature = "profiling")]
    let mut last = input_started;
    #[cfg(feature = "profiling")]
    let mut profiling = super::profiling::Session::new();
    #[cfg(feature = "profiling")]
    let mut pending_started = 0;
    #[cfg(feature = "profiling")]
    let mut pending_screen = engine.screen();
    loop {
        if pending_swap.as_ref().is_some_and(Hub75Swap::is_done) {
            frame = Some(pending_swap.take().expect("completed swap").wait());
            #[cfg(feature = "profiling")]
            profiling.record(
                pending_screen,
                2,
                Instant::now().as_micros() - pending_started,
            );
        }
        let batch = super::buttons::drain();
        #[cfg(feature = "profiling")]
        profiling.poll(batch.cutoff_us);
        activity.set_high();
        #[cfg(feature = "profiling")]
        let update_start = Instant::now().as_micros();
        let update = runtime.update(&mut engine, &batch);
        #[cfg(feature = "profiling")]
        {
            profiling.record(
                engine.screen(),
                0,
                Instant::now().as_micros() - update_start,
            );
            profiling.record(engine.screen(), 3, batch.cutoff_us.saturating_sub(last));
            last = batch.cutoff_us;
        }
        super::audio_worker::request(update.audio, runtime.audio_enabled());
        redraw |= update.redraw;
        activity.set_low();
        if redraw && let Some(back) = frame.take() {
            #[cfg(feature = "profiling")]
            let render_start = Instant::now().as_micros();
            let mut target = if engine.screen() == Screen::App(AppId::Canvas) {
                PanelTarget::canvas(&mut *back)
            } else {
                PanelTarget::native(&mut *back)
            };
            engine.render(&mut target).unwrap();
            #[cfg(feature = "profiling")]
            {
                profiling.record(
                    engine.screen(),
                    1,
                    Instant::now().as_micros() - render_start,
                );
                pending_started = Instant::now().as_micros();
                pending_screen = engine.screen();
            }
            match hub75.swap(back) {
                Ok(swap) => {
                    pending_swap = Some(swap);
                    redraw = false;
                }
                Err((_, returned)) => {
                    defmt::error!("HUB75 swap rejected");
                    frame = Some(returned);
                }
            }
        }
        // Absolute deadline survives unrelated USB/input wakeups without drift.
        let deadline = engine.next_update_after().map(|after| {
            Instant::from_micros(batch.cutoff_us.saturating_add(after.as_micros() as u64))
        });
        select4(
            super::buttons::changed(),
            async {
                match deadline {
                    Some(at) => Timer::at(at).await,
                    None => pending::<()>().await,
                }
            },
            usb.service(&mut engine),
            async {
                match pending_swap.as_mut() {
                    Some(swap) => swap.wait_for_done().await,
                    None => pending::<()>().await,
                }
            },
        )
        .await;
    }
}
