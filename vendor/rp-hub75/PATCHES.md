# Local changes to rp-hub75 0.1.1

This is the crates.io 0.1.1 package, retained with its original licenses and
sources. The project patches crates.io resolution to this directory.

The Embassy RP2040 backend previously indexed the raw DMA `INTR` accessor by
IRQ line. RP2040 has a single raw status register at DMA offset `0x400`; index 1
addresses reserved offset `0x410`, so IRQ1 completion could not be acknowledged
correctly. Both selected IRQ lines now read/clear raw bank 0. Only the supplied
channel bit is acknowledged. RP2350 behavior is unchanged by this scoped patch.

Primary reference: Raspberry Pi's
[RP2040 DMA register definitions](https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2040/hardware_regs/include/hardware/regs/dma.h)
(`DMA_INTR_OFFSET`, `DMA_INTE1_OFFSET`, `DMA_INTS1_OFFSET`). The pinned HAL backend
also uses the same single raw register. Re-evaluate this patch when updating the
upstream dependency.
