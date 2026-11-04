/* onset_detector.c - replaceable log-spectral-flux baseline.
 *
 * Definition used here (documented, NOT claimed to be Essentia-identical):
 *   X_t[k]  = log(1 + A_t[k] / A_ref)
 *   flux_t  = mean_k( max(0, X_t[k] - X_{t-1}[k]) )   over bin lo..hi
 *   E_t     = A[0]^2 + A[2048]^2 + 2*sum_{k=1..2047} A[k]^2
 *   L_t     = 10*log10(max(E_t, 1e-12))
 * L is a spectral-energy proxy in the same window/scaling, not PCM RMS/dBFS.
 */
#include "onset_detector.h"
#include <math.h>
#include <string.h>

static float ClampF(float v, float lo, float hi)
{
    if (v < lo) {
        return lo;
    }
    if (v > hi) {
        return hi;
    }
    return v;
}

static void SortFloats(float *a, int n)
{
    int i, j;
    for (i = 1; i < n; ++i) {
        float v = a[i];
        j = i - 1;
        while ((j >= 0) && (a[j] > v)) {
            a[j + 1] = a[j];
            --j;
        }
        a[j + 1] = v;
    }
}

static float MedianOf(const float *src, int n)
{
    float tmp[32];
    int i;
    if ((n <= 0) || (n > 32)) {
        return 0.0f;
    }
    for (i = 0; i < n; ++i) {
        tmp[i] = src[i];
    }
    SortFloats(tmp, n);
    if ((n & 1) != 0) {
        return tmp[n / 2];
    }
    return 0.5f * (tmp[n / 2 - 1] + tmp[n / 2]);
}

void OnsetInit(OnsetContext *ctx, const NoteConfig *cfg)
{
    (void)cfg;
    if (ctx == 0) {
        return;
    }
    memset(ctx, 0, sizeof(*ctx));
    ctx->armed = 1U;
}

void OnsetReset(OnsetContext *ctx)
{
    if (ctx == 0) {
        return;
    }
    memset(ctx->prev_log, 0, sizeof(ctx->prev_log));
    ctx->prev_level_db = 0.0f;
    ctx->hist_count = 0U;
    ctx->hist_pos = 0U;
    ctx->has_prev = 0U;
    ctx->armed = 1U;
    ctx->pending_peak = 0U;
    ctx->pending_audible = 0U;
    ctx->pending_flux = 0.0f;
    ctx->pending_level_before = 0.0f;
    ctx->pending_sample = 0U;
    ctx->have_last_onset = 0U;
    ctx->last_onset_sample = 0U;
    /* calibration and noise_db are preserved */
}

void OnsetCalibStart(OnsetContext *ctx)
{
    if (ctx == 0) {
        return;
    }
    ctx->calibrating = 1U;
    ctx->calib_count = 0U;
}

int OnsetCalibReady(const OnsetContext *ctx)
{
    return ((ctx != 0) && (ctx->calibrated != 0U) && (ctx->calibrating == 0U));
}

float OnsetNoiseDb(const OnsetContext *ctx)
{
    return (ctx != 0) ? ctx->noise_db : 0.0f;
}

void OnsetProcess(OnsetContext *ctx, const NoteConfig *cfg,
                  const AudioNoteFrame *f, const float *mag,
                  OnsetResult *out)
{
    uint32_t k;
    uint32_t lo, hi;
    uint64_t feature;
    uint64_t window_end;
    double energy = 0.0;
    float level_db;
    float flux = 0.0f;
    float threshold;
    float gate_base;
    int audible;
    int quiet;

    if ((ctx == 0) || (cfg == 0) || (f == 0) || (mag == 0) || (out == 0)) {
        return;
    }
    memset(out, 0, sizeof(*out));
    feature = f->first_sample + (uint64_t)(f->n_fft / 2U);
    window_end = f->first_sample + (uint64_t)f->n_fft;
    out->decision_sample = window_end;
    out->calibrated = ctx->calibrated;
    out->history_valid = ctx->has_prev;

    lo = cfg->onset_band_lo;
    hi = cfg->onset_band_hi;
    if (lo < 1U) {
        lo = 1U;
    }
    if (hi >= NOTE_MAG_BINS) {
        hi = NOTE_MAG_BINS - 1U;
    }
    if (hi <= lo) {
        out->reason = 6;
        ctx->has_prev = 0U;
        return;
    }

    for (k = 0U; k < NOTE_MAG_BINS; ++k) {
        if (!isfinite(mag[k]) || (mag[k] < 0.0f)) {
            out->reason = 6; /* bad spectrum, do not diff against it */
            ctx->has_prev = 0U;
            ctx->pending_peak = 0U;
            return;
        }
    }

    /* Spectral energy proxy over the whole window. */
    energy = (double)mag[0] * (double)mag[0] +
             (double)mag[NOTE_MAG_BINS - 1U] * (double)mag[NOTE_MAG_BINS - 1U];
    for (k = 1U; k < (NOTE_MAG_BINS - 1U); ++k) {
        energy += 2.0 * (double)mag[k] * (double)mag[k];
    }
    level_db = (float)(10.0 * log10(energy > 1e-12 ? energy : 1e-12));
    out->level_db = level_db;
    out->level_db_before = ctx->prev_level_db;

    if (ctx->has_prev == 0U) {
        for (k = lo; k <= hi; ++k) {
            ctx->prev_log[k] = logf(1.0f + mag[k] / cfg->onset_aref);
        }
        ctx->prev_level_db = level_db;
        ctx->has_prev = 1U;
        out->reason = 1; /* no history: not evidence of silence */
        out->armed = ctx->armed;
        return;
    }

    for (k = lo; k <= hi; ++k) {
        float x = logf(1.0f + mag[k] / cfg->onset_aref);
        float d = x - ctx->prev_log[k];
        if (d > 0.0f) {
            flux += d;
        }
        ctx->prev_log[k] = x;
    }
    flux /= (float)(hi - lo + 1U);
    out->flux = flux;

    /* Threshold from PAST flux only. */
    if (ctx->hist_count < 4U) {
        threshold = cfg->onset_flux_floor;
        out->armed = 0U;
    } else {
        int n = (int)ctx->hist_count;
        float med = MedianOf(ctx->hist, n);
        float dev[31];
        int i;
        for (i = 0; i < n; ++i) {
            float d = ctx->hist[i] - med;
            dev[i] = (d < 0.0f) ? -d : d;
        }
        threshold = med + cfg->onset_alpha * MedianOf(dev, n);
        if (threshold < cfg->onset_flux_floor) {
            threshold = cfg->onset_flux_floor;
        }
        out->armed = ctx->armed;
    }
    out->threshold = threshold;

    gate_base = (ctx->calibrated != 0U) ? ctx->noise_db : cfg->fixed_quiet_db;
    audible = (level_db >= (gate_base + cfg->onset_gate_db)) ? 1 : 0;
    quiet = (level_db < (gate_base + cfg->onset_release_db)) ? 1 : 0;
    out->audible = (uint8_t)audible;
    out->quiet = (uint8_t)quiet;

    if (ctx->calibrating != 0U) {
        if (ctx->calib_count < 32U) {
            ctx->calib_levels[ctx->calib_count++] = level_db;
        }
        if (ctx->calib_count >= cfg->onset_calib_frames) {
            ctx->noise_db = MedianOf(ctx->calib_levels, (int)ctx->calib_count);
            ctx->calibrated = 1U;
            ctx->calibrating = 0U;
        }
        out->reason = 7;
        out->calibrated = ctx->calibrated;
        ctx->prev_level_db = level_db;
        ctx->hist[ctx->hist_pos] = flux;
        ctx->hist_pos = (uint8_t)((ctx->hist_pos + 1U) % 31U);
        if (ctx->hist_count < 31U) {
            ctx->hist_count++;
        }
        return;
    }

    /* Peak confirmation: a local maximum is required; plateaus trigger once. */
    if (ctx->pending_peak != 0U) {
        if (flux < ctx->pending_flux) {
            out->valid = 1U;
            out->onset_sample = ctx->pending_sample;
            out->strength = ctx->pending_flux;
            out->level_db_before = ctx->pending_level_before;
            out->decision_sample = window_end;
            ctx->pending_peak = 0U;
            ctx->have_last_onset = 1U;
            ctx->last_onset_sample = ctx->pending_sample;
        } else {
            ctx->pending_flux = flux;
            ctx->pending_sample = feature;
            out->reason = 5;
        }
    } else if ((flux > threshold) && (ctx->armed != 0U) && (audible != 0)) {
        if ((ctx->have_last_onset != 0U) &&
            ((feature - ctx->last_onset_sample) <
             (uint64_t)cfg->repeat_min_interval_samples)) {
            out->reason = 4;
        } else {
            ctx->pending_peak = 1U;
            ctx->pending_audible = (uint8_t)audible;
            ctx->pending_flux = flux;
            ctx->pending_sample = feature;
            ctx->pending_level_before = ctx->prev_level_db;
            ctx->armed = 0U;
            out->reason = 5;
        }
    } else if (flux <= threshold) {
        out->reason = 3;
    }

    if (ctx->pending_peak == 0U) {
        if (cfg->onset_require_fall != 0U) {
            if (flux < (threshold * cfg->onset_fall_ratio)) {
                ctx->armed = 1U;
            }
        } else {
            ctx->armed = 1U;
        }
    }

    ctx->hist[ctx->hist_pos] = flux;
    ctx->hist_pos = (uint8_t)((ctx->hist_pos + 1U) % 31U);
    if (ctx->hist_count < 31U) {
        ctx->hist_count++;
    }
    ctx->prev_level_db = level_db;
    out->armed = ctx->armed;
    out->calibrated = ctx->calibrated;
    out->strength = (out->valid != 0U) ? out->strength : flux;
    (void)ClampF;
}
