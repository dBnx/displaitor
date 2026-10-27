#define QOA_IMPLEMENTATION
#define QOA_NO_STDIO
#include "qoa.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define SAMPLE_COUNT 5257

static int write_bytes(const char *path, const void *data, size_t len) {
	FILE *file = fopen(path, "wb");
	if (!file) return 0;
	int ok = fwrite(data, 1, len, file) == len;
	return fclose(file) == 0 && ok;
}

int main(int argc, char **argv) {
	if (argc != 3) return 2;
	short input[SAMPLE_COUNT];
	uint32_t state = 0x6d2b79f5u;
	for (uint32_t i = 0; i < SAMPLE_COUNT; i++) {
		state ^= state << 13;
		state ^= state >> 17;
		state ^= state << 5;
		input[i] = (short)(state >> 16);
	}

	qoa_desc encoder = {0};
	encoder.channels = 1;
	encoder.samplerate = 22050;
	encoder.samples = SAMPLE_COUNT;
	unsigned int encoded_size = 0;
	unsigned char *encoded = qoa_encode(input, &encoder, &encoded_size);
	if (!encoded || !write_bytes(argv[1], encoded, encoded_size)) return 1;

	qoa_desc decoder = {0};
	short *decoded = qoa_decode(encoded, encoded_size, &decoder);
	if (!decoded || decoder.samples != SAMPLE_COUNT) return 1;
	unsigned char pcm[SAMPLE_COUNT * 2];
	for (unsigned int i = 0; i < SAMPLE_COUNT; i++) {
		unsigned short bits = (unsigned short)decoded[i];
		pcm[i * 2] = (unsigned char)(bits & 0xff);
		pcm[i * 2 + 1] = (unsigned char)(bits >> 8);
	}
	int ok = write_bytes(argv[2], pcm, sizeof(pcm));
	QOA_FREE(decoded);
	QOA_FREE(encoded);
	return ok ? 0 : 1;
}
