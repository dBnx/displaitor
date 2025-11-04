# AGENTS.md 


## Structure

This rust workspace hosts many different libraries and executables for different architectures. Those are:
- `aitos` The main repository for the FW and targets the RP2040 (ARM).
- `displaitor` The main library to create the UI. Used in the RP2040 or on the native host. Does not contain a binary
- `simulaitor` Helper binary, that runs the UI library so it can be debugged on the host platform.
- `qoa_decoder` Helper library to decode image files in QOA format.


## Code 

- Be aware about embedded constaints in the FW and the displaitor library.
- Use best practices and use `cargo check` and `cargo clippy` often.
- Use `cargo clean` between compiling for different architectures (native or the microcontroller).
- Use conventinal commit messages.
- Use a timeout when running the simulaitor binary. Otherwise it will never quit.