/* Offline-only wrapper for the upstream QOA encoder. No code runs on the MCU. */
#define QOA_IMPLEMENTATION
#include "qoa.h"
#include <stdint.h>

int main(int argc, char **argv) {
    if (argc != 5) return 2;
    unsigned long rate = strtoul(argv[1], NULL, 10);
    if (!rate || rate > 192000) return 2;
    FILE *input = fopen(argv[2], "rb");
    if (!input) return 1;
    if (fseek(input, 0, SEEK_END)) { fclose(input); return 1; }
    long length = ftell(input);
    if (length <= 0 || length > 384000 || length % 2 || fseek(input, 0, SEEK_SET)) {
        fclose(input); return 1;
    }
    short *samples = malloc((size_t)length);
    if (!samples) { fclose(input); return 1; }
    for (long i = 0; i < length / 2; i++) {
        int low = fgetc(input), high = fgetc(input);
        if (low == EOF || high == EOF) { free(samples); fclose(input); return 1; }
        samples[i] = (short)(low | high << 8);
    }
    fclose(input);
    qoa_desc format = {0};
    format.channels = 1;
    format.samplerate = (unsigned int)rate;
    format.samples = (unsigned int)(length / 2);
    int ok = qoa_write(argv[3], samples, &format) > 0;
    free(samples);
    if (!ok) return 1;
    short *decoded = qoa_read(argv[3], &format);
    if (!decoded || format.samples != (unsigned int)(length / 2)) { free(decoded); return 1; }
    FILE *output = fopen(argv[4], "wb");
    if (!output) { free(decoded); return 1; }
    for (unsigned int i = 0; i < format.samples; i++) {
        unsigned short value = (unsigned short)decoded[i];
        if (fputc(value & 255, output) == EOF || fputc(value >> 8, output) == EOF) ok = 0;
    }
    free(decoded);
    if (fclose(output)) ok = 0;
    return ok ? 0 : 1;
}
