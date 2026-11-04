#ifndef SPECTRUM_PROTOCOL_H
#define SPECTRUM_PROTOCOL_H
#include <stdint.h>
#define SPEC_HEADER_WORDS 16U
#define SPEC_BINS 2049U
#define SPEC_WORDS (SPEC_HEADER_WORDS + SPEC_BINS)
#define SPEC_BYTES (SPEC_WORDS * 4U)
#define SPEC_BUFFER_WORDS 2080U /* 8320 B: whole isolated 64-byte blocks */
enum { SPEC_OK=0, SPEC_BAD_HEADER=1, SPEC_BAD_BIN=2, SPEC_FRAME_ERROR=3,
       SPEC_PEAK_MISMATCH=4, SPEC_NEIGHBOR_MISMATCH=5, SPEC_BAD_SEQUENCE=6 };
typedef struct {
    uint32_t frame, first_lo, first_hi, flags, dropped, source_drop, fft_count;
    uint32_t pl_bin, pl_mag, ps_bin, ps_mag;
} SpectrumInfo;

/* Same interval, threshold, local-maximum and tie rules as fft_peak_search.v.
 * Full spectrum includes DC, Nyquist and below-threshold data unchanged.
 * Do not pass flagged frames to pitch or UI as valid measurements.
 */
static int SpectrumValidate(const volatile uint32_t *w, uint32_t words, SpectrumInfo *v)
{
    uint32_t k, best_bin=0U, best_mag=0U;
    if (words != SPEC_WORDS || w[0] != 0x53504543U || w[1] != 0x00020040U ||
        w[2] != SPEC_BYTES || w[6] != 16000U || w[7] != 0x02001000U ||
        w[8] != 0x00010801U || w[9] != 0x00011557U) return SPEC_BAD_HEADER;
    v->frame=w[3]; v->first_lo=w[4]; v->first_hi=w[5];
    v->flags=w[10]; v->dropped=w[11]; v->source_drop=w[14]; v->fft_count=w[15];
    v->pl_bin=w[12]>>16; v->pl_mag=w[12]&65535U;
    v->ps_bin=0U; v->ps_mag=0U;
    for (k=0U;k<SPEC_BINS;++k) if ((w[16U+k]>>16)!=k) return SPEC_BAD_BIN;
    if (v->flags != 0U || v->fft_count != 4096U || v->source_drop != 0U) return SPEC_FRAME_ERROR;
    for (k=13U;k<=512U;++k) {
        uint32_t m=w[16U+k]&65535U;
        if (m>=100U && m>best_mag && m>=(w[15U+k]&65535U) && m>(w[17U+k]&65535U)) {
            best_mag=m; best_bin=k;
        }
    }
    v->ps_bin=best_bin; v->ps_mag=best_mag;
    if (v->pl_bin!=best_bin || v->pl_mag!=best_mag) return SPEC_PEAK_MISMATCH;
    if (best_mag==0U) {
        if (w[13]!=0U) return SPEC_NEIGHBOR_MISMATCH;
    } else if (w[13]!=(((w[15U+best_bin]&65535U)<<16)|(w[17U+best_bin]&65535U))) {
        return SPEC_NEIGHBOR_MISMATCH;
    }
    return SPEC_OK;
}
/* State is advanced only after a fully accepted packet. Restart with PL. */
typedef struct { uint64_t first; uint32_t frame; int have; } SpectrumSequence;
static int SpectrumCheckSequence(SpectrumSequence *s, const SpectrumInfo *v, uint32_t *gap)
{
    uint64_t first=((uint64_t)v->first_hi<<32)|v->first_lo;
    uint32_t delta=v->frame-s->frame;
    *gap=0U;
    if (first!=(uint64_t)v->frame*512ULL) return SPEC_BAD_SEQUENCE;
    if (s->have && (!delta || (delta&0x80000000U) || first-s->first!=(uint64_t)delta*512ULL))
        return SPEC_BAD_SEQUENCE;
    if (s->have) *gap=delta-1U;
    s->first=first; s->frame=v->frame; s->have=1;
    return SPEC_OK;
}
#endif
