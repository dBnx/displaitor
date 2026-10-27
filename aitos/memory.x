/* Original board: RP2040 with 16 MiB external flash.
 * Both modes reserve 16 KiB for core 0's descending stack. Core 1's stack is
 * a static allocation in RAM and is therefore included in the linker budget.
 */
MEMORY {
    BOOT2 : ORIGIN = 0x10000000, LENGTH = 0x100
    FLASH : ORIGIN = 0x10000100, LENGTH = 16M - 0x100
    RAM   : ORIGIN = 0x20000000, LENGTH = 240K
    STACK0 : ORIGIN = 0x2003C000, LENGTH = 16K
}
_stack_end = ORIGIN(STACK0);
_stack_start = ORIGIN(STACK0) + LENGTH(STACK0);
SECTIONS {
    .boot2 ORIGIN(BOOT2) : { KEEP(*(.boot2)); } > BOOT2
} INSERT BEFORE .text;
