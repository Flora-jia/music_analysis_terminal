/* onset_detector.h - log-spectral-flux onset baseline over the 4096-point spectrum.
 *
 * This is the "replaceable baseline": it consumes the existing 2049 linear
 * magnitude bins. A future 1024-point short-window source can replace it
 * without changing NoteTracker's interface.
 */
#ifndef ONSET_DETECTOR_H
#define ONSET_DETECTOR_H

#include "audio_note_types.h"

typedef struct {
    uint8_t  valid;             /* a confirmed onset in this frame */
    uint8_t  history_valid;     /* previous spectrum existed */
    uint8_t  calibrated;        /* noise floor came from a real calibration */
    uint8_t  armed;             /* rearmed and allowed to trigger */
    uint8_t  audible;
    uint8_t  quiet;
    int      reason;            /* 0 ok, 1 no history, 2 below gate,
                                   3 not armed, 4 min interval, 5 peak pending,
                                   6 bad input, 7 calibrating */
    float    flux;
    float    threshold;
    float    strength;
    float    level_db;
    float    level_db_before;
    uint64_t onset_sample;      /* feature_sample of the peak frame */
    uint64_t decision_sample;   /* window_end of the confirming frame */
} OnsetResult;

typedef struct {
    float    prev_log[NOTE_MAG_BINS]; /* previous log-compressed band values */
    float    prev_level_db;
    float    hist[31];
    uint8_t  hist_count;
    uint8_t  hist_pos;
    uint8_t  has_prev;
    uint8_t  armed;
    uint8_t  pending_peak;
    uint8_t  pending_audible;
    float    pending_flux;
    float    pending_level_before;
    uint64_t pending_sample;
    float    noise_db;
    uint8_t  calibrated;
    uint8_t  calibrating;
    uint8_t  calib_count;
    float    calib_levels[32];
    uint8_t  have_last_onset;
    uint64_t last_onset_sample;
} OnsetContext;

void OnsetInit(OnsetContext *ctx, const NoteConfig *cfg);
void OnsetReset(OnsetContext *ctx);          /* keep calibration, drop history */
void OnsetCalibStart(OnsetContext *ctx);
int  OnsetCalibReady(const OnsetContext *ctx);
float OnsetNoiseDb(const OnsetContext *ctx);

/* mag: 2049 linear magnitudes, read-only. */
void OnsetProcess(OnsetContext *ctx, const NoteConfig *cfg,
                  const AudioNoteFrame *f, const float *mag,
                  OnsetResult *out);

#endif /* ONSET_DETECTOR_H */
