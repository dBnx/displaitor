//! Flash-to-SRAM executable relocation before cortex-m-rt or Embassy runs.
//!
//! Only executable sections and the vector table move. Readonly assets retain
//! their Flash addresses, so XIP must remain enabled throughout normal operation.
//! The assembly uses no initialized RAM, stack, or callable Rust code.

core::arch::global_asm!(
    r#"
    .syntax unified
    .cpu cortex-m0plus
    .thumb

    .section .boot_vectors, "a"
    .word _stack_start
    .word RamBoot
    .rept 46
    .word RamBootFault
    .endr

    .section .ram_boot, "ax"
    .global RamBoot
    .type RamBoot, %function
    .thumb_func
RamBoot:
    cpsid i
    ldr r0, =__vector_table
    ldr r1, =__evector
    ldr r2, =__sivector
1:
    cmp r0, r1
    bhs 2f
    ldm r2!, {{r3}}
    stm r0!, {{r3}}
    b 1b
2:
    ldr r0, =__stext
    ldr r1, =__etext
    ldr r2, =__sitext
3:
    cmp r0, r1
    bhs 4f
    ldm r2!, {{r3}}
    stm r0!, {{r3}}
    b 3b
4:
    dsb
    isb
    ldr r0, =__vector_table
    ldr r1, =0xe000ed08
    str r0, [r1]
    dsb
    isb
    ldm r0!, {{r1, r2}}
    msr msp, r1
    cpsie i
    bx r2
    .size RamBoot, . - RamBoot

    .global RamBootFault
    .type RamBootFault, %function
    .thumb_func
RamBootFault:
    cpsid i
5:
    b 5b
    .size RamBootFault, . - RamBootFault
    .ltorg
"#
);
