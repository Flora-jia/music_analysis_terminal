#include <stdio.h>
#include "../merged_inputs/spectrum_protocol.h"
int main(void) {
    FILE *fp = fopen("tests/fixtures/spectrum_packets.hex", "r");
    uint32_t data[SPEC_BUFFER_WORDS], gap = 0;
    SpectrumSequence sequence = {0};
    SpectrumInfo info;
    unsigned f, k;
    if (!fp) return 10;
    for (f = 0; f < 3; ++f) {
        for (k = 0; k < SPEC_WORDS; ++k)
            if (fscanf(fp, "%x", &data[k]) != 1) return 11;
        if (SpectrumValidate(data, SPEC_WORDS, &info) != SPEC_OK) return 12;
        if (SpectrumCheckSequence(&sequence, &info, &gap) != SPEC_OK) return 13;
        if (gap != (f == 2 ? 1U : 0U)) return 14;
    }
    data[10] = 1;
    if (SpectrumValidate(data, SPEC_WORDS, &info) != SPEC_FRAME_ERROR) return 15;
    data[10] = 0; data[16 + 100] ^= 0x10000U;
    if (SpectrumValidate(data, SPEC_WORDS, &info) != SPEC_BAD_BIN) return 16;
    fclose(fp);
    puts("SPEC_C_PROTOCOL_PASS: actual RTL packets, peak/neighbors, sequence gap, corruption rejection");
    return 0;
}
