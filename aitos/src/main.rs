//! Offline-buildable firmware for the original Displaitor RP2040 board.
#![cfg_attr(target_os = "none", no_std)]
#![cfg_attr(target_os = "none", no_main)]

#[cfg(target_os = "none")]
mod audio_dma;
#[cfg(target_os = "none")]
mod audio_worker;
#[cfg(target_os = "none")]
mod board;
#[cfg(target_os = "none")]
mod buttons;
#[cfg(all(target_os = "none", feature = "profiling"))]
mod profiling;
#[cfg(all(target_os = "none", feature = "ram-code"))]
mod ram_boot;
#[cfg(target_os = "none")]
mod usb_canvas;

#[cfg(not(target_os = "none"))]
fn main() {
    eprintln!("Build firmware with --target thumbv6m-none-eabi --features firmware");
    std::process::exit(1);
}
