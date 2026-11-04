/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Algorithm ports/adaptations of MTG sms-tools and Essentia; see REFERENCES.md.
 * Fixed input: 2049 LINEAR amplitude bins of a 4096-point Hann FFT, fs=16000.
 */
#ifndef PITCH_COMPARE_H
#define PITCH_COMPARE_H
#define PITCH_N 4096
#define PITCH_BINS 2049
#define PITCH_MAX_PEAKS 64
#define PITCH_SALIENCE_BINS 900
#define PITCH_TWM 1U
#define PITCH_SALIENCE 2U
#define PITCH_YINFFT 4U
enum { PITCH_OK=0, PITCH_QUIET=1, PITCH_NO_ESTIMATE=2, PITCH_BAD_INPUT=3, PITCH_DISABLED=4 };
enum { PITCH_MODE_CORE=0, PITCH_MODE_EXTENDED=1, PITCH_MODE_SINGLE_PEAK=2 };
typedef struct {
    float min_hz, max_hz, min_peak, min_peak_median_ratio;
    float relative_peak_db, peak_floor, twm_max_error, yin_min_confidence;
    int twm_subharmonics, yin_first_minimum;
} PitchConfig;
typedef struct {
    float frequency, score;
    int midi, valid, reason, mode;
} PitchResult;
typedef struct {
    PitchResult twm, salience, yinfft;
    float peak_amplitude, median_amplitude, dominant_hz;
    int peak_count, gate_reason;
} PitchReport;
void PitchDefaultConfig(PitchConfig *c);
void PitchInit(void);
void PitchAnalyze(const float *magnitude, const PitchConfig *c, unsigned mask, PitchReport *r);
void PitchNoteName(int midi, char *out, unsigned size);
/* Public numerical cores also used by independent host reference tests. */
float PitchTwmCore(const float *freq, const float *db, int count,
                   const float *candidates, int nc, float *error);
int PitchSalienceCore(const float *freq, const float *mag, int count,
                      float min_hz, float max_hz, float *curve);
int PitchYinCurve(const float *mag, float *curve);
void PitchRunTwm(const PitchConfig *c, PitchResult *r);
void PitchRunSalience(const PitchConfig *c, PitchResult *r);
void PitchRunYinFFT(const PitchConfig *c, PitchResult *r);
int PitchPrepare(const float *mag, const PitchConfig *c, PitchReport *report);
#endif
