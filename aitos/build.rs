use std::{env, fs, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-changed=memory.x");
    println!("cargo:rerun-if-changed=ram-code.x");
    if env::var("TARGET").as_deref() == Ok("thumbv6m-none-eabi") {
        let out = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo sets OUT_DIR"));
        fs::write(out.join("memory.x"), include_bytes!("memory.x"))
            .expect("copy linker memory map");
        let linker: &[u8] = if env::var_os("CARGO_FEATURE_RAM_CODE").is_some() {
            include_bytes!("ram-code.x")
        } else {
            b"/* Standard Flash execution. */\nINCLUDE link.x\n"
        };
        fs::write(out.join("aitos-link.x"), linker).expect("write selected runtime linker script");
        println!("cargo:rustc-link-search={}", out.display());
    }
}
