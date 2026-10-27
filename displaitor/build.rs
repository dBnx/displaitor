use std::{env, fs, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=DISPLAITOR_NAMES_FILE");
    let source = env::var_os("DISPLAITOR_NAMES_FILE").map_or_else(
        || PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("assets/names.example.txt"),
        PathBuf::from,
    );
    assert!(
        source.is_absolute(),
        "DISPLAITOR_NAMES_FILE must be an absolute path"
    );
    println!("cargo:rerun-if-changed={}", source.display());
    let output = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo supplies OUT_DIR"));
    fs::copy(&source, output.join("names.txt")).expect("read the configured names file");
}
