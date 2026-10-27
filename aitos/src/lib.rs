//! Allocation-free firmware policies and target-independent adapter boundaries.
#![no_std]
#![forbid(unsafe_code)]

pub mod audio;
pub mod display;
pub mod input;
pub mod runtime;
pub mod usb_staging;

#[cfg(any(test, all(target_arch = "arm", target_os = "none")))]
pub mod usb_bridge;
