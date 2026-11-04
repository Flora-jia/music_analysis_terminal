/* note_tracker.c - note state machine, stage A. */
#include "note_tracker.h"
#include <string.h>

void NoteDefaultConfig(NoteConfig *c)
{
    if (c == 0) {
        return;
    }
    memset(c, 0, sizeof(*c));
    c->session_id = 1U;
    c->start_confirm_frames = 2U;
    c->change_confirm_frames = 2U;
    c->quiet_release_frames = 2U;
    c->pitch_lost_frames = 3U;
    c->yin_min_score = 0.80f;
    c->onset_association_samples = 2048U;
    c->repeat_min_interval_samples = 1536U;
    c->stream_watchdog_us = 128000U;

    c->onset_band_lo = 2U;
    c->onset_band_hi = 1280U;
    c->onset_aref = 1.0f;
    c->onset_history_len = 31U;
    c->onset_alpha = 3.0f;
    c->onset_flux_floor = 0.002f;
    c->onset_gate_db = 6.0f;
    c->onset_release_db = 3.0f;
    c->reattack_db = 3.0f;
    c->reattack_dip_db = 6.0f;
    c->onset_require_fall = 1U;
    c->onset_fall_ratio = 0.5f;
    c->onset_calib_frames = 16U;
    c->fixed_quiet_db = -70.0f;
}

static uint32_t FreqMilliHz(float hz)
{
    if (!(hz > 0.0f) || (hz > 1.0e6f)) {
        return 0U;
    }
    return (uint32_t)(hz * 1000.0f + 0.5f);
}

static int32_t ScoreMilli(float s)
{
    if (!(s > -1.0e6f) || !(s < 1.0e6f)) {
        return 0;
    }
    return (int32_t)(s * 1000.0f);
}

static uint64_t ClampSample(uint64_t v, uint64_t lo, uint64_t hi)
{
    if (v < lo) {
        return lo;
    }
    if (v > hi) {
        return hi;
    }
    return v;
}

static void PushEvent(NoteTracker *t, uint8_t type, uint8_t reason,
                      uint8_t tq, uint32_t note_id, int midi,
                      float hz, float score, uint32_t frame_id,
                      uint64_t start_sample, uint64_t end_sample,
                      uint64_t decision_sample, uint32_t fs)
{
    NoteEvent ev;
    memset(&ev, 0, sizeof(ev));
    ev.schema_version = NOTE_SCHEMA_VERSION;
    ev.session_id = t->session_id;
    ev.event_seq = (t->queue != 0) ? (t->queue->pushed + 1U) : 0U;
    ev.type = type;
    ev.reason = reason;
    ev.time_quality = tq;
    ev.flags = 0U;
    ev.note_id = note_id;
    ev.midi = (uint8_t)((midi < 0) ? 0 : (midi > 127 ? 127 : midi));
    ev.frequency_millihz = FreqMilliHz(hz);
    ev.pitch_score_milli = ScoreMilli(score);
    ev.frame_id = frame_id;
    ev.start_sample = start_sample;
    ev.end_sample = end_sample;
    ev.decision_sample = decision_sample;
    ev.fs = fs;
    if ((t->queue != 0) && !NoteEventQueuePush(t->queue, &ev)) {
        /* Queue full: overflow already counted inside the queue. */
        t->current.tracking_valid = 0U;
    }
}

static void UpdateCurrent(NoteTracker *t, const AudioNoteFrame *f,
                          int midi, float hz, float score, uint8_t tq)
{
    t->current.session_id = t->session_id;
    t->current.note_id = t->cur_note_id;
    t->current.active = (uint8_t)(t->state == NOTE_ST_ACTIVE);
    t->current.tracking_valid = 1U;
    t->current.midi = (uint8_t)((midi < 0) ? 0 : midi);
    t->current.reason = (uint8_t)NOTE_REASON_START;
    t->current.time_quality = tq;
    t->current.frequency_hz = hz;
    t->current.pitch_score = score;
    t->current.frame_id = f->frame_id;
    t->current.feature_sample = f->first_sample + (uint64_t)(f->n_fft / 2U);
    t->current.decision_sample = f->first_sample + (uint64_t)f->n_fft;
}

static int FrameContinuous(const NoteTracker *t, const AudioNoteFrame *f,
                           uint32_t prev_frame, uint64_t prev_first)
{
    (void)t;
    return (f->frame_id == (prev_frame + 1U)) &&
           (f->first_sample == (prev_first + (uint64_t)f->hop));
}

static void ClearCandidates(NoteTracker *t)
{
    t->cand_midi = -1;
    t->cand_count = 0U;
    t->cand_start_sample = 0U;
    t->cand_frame = 0U;
    t->cand_first_sample = 0U;
    t->change_midi = -1;
    t->change_count = 0U;
    t->change_first_sample = 0U;
    t->change_frame = 0U;
    t->change_feature_sample = 0U;
}

static void PushLevel(NoteTracker *t, float level_db)
{
    t->level_recent[t->level_pos] = level_db;
    t->level_pos = (uint8_t)((t->level_pos + 1U) % 8U);
    if (t->level_count < 8U) {
        t->level_count++;
    }
}

static float MinRecentLevel(const NoteTracker *t)
{
    float m = 1.0e9f;
    uint8_t i;
    for (i = 0U; i < t->level_count; ++i) {
        if (t->level_recent[i] < m) {
            m = t->level_recent[i];
        }
    }
    return (t->level_count > 0U) ? m : 0.0f;
}

static void EmitOn(NoteTracker *t, const AudioNoteFrame *f,
                   int midi, float hz, float score,
                   uint64_t start_sample, uint64_t boundary,
                   uint8_t reason, uint8_t tq)
{
    t->cur_note_id = t->next_note_id++;
    t->cur_midi = (int16_t)midi;
    t->start_sample = start_sample;
    t->last_valid_sample = f->first_sample + (uint64_t)(f->n_fft / 2U);
    t->state = NOTE_ST_ACTIVE;
    t->current.session_id = t->session_id;
    t->current.note_id = t->cur_note_id;
    t->current.active = 1U;
    t->current.tracking_valid = 1U;
    t->current.midi = (uint8_t)midi;
    t->current.reason = reason;
    t->current.time_quality = tq;
    t->current.frequency_hz = hz;
    t->current.pitch_score = score;
    t->current.frame_id = f->frame_id;
    t->current.feature_sample = f->first_sample + (uint64_t)(f->n_fft / 2U);
    t->current.decision_sample = f->first_sample + (uint64_t)f->n_fft;

    PushEvent(t, (uint8_t)NOTE_EV_ON, reason, tq, t->cur_note_id, midi,
              hz, score, f->frame_id, start_sample, 0U,
              f->first_sample + (uint64_t)f->n_fft, f->fs);
    (void)boundary;
}

static void EmitOff(NoteTracker *t, const AudioNoteFrame *f,
                    uint64_t end_sample, uint8_t reason, uint8_t tq)
{
    if (t->state != NOTE_ST_ACTIVE) {
        return;
    }
    if (end_sample < t->start_sample) {
        end_sample = t->start_sample;
    }
    PushEvent(t, (uint8_t)NOTE_EV_OFF, reason, tq, t->cur_note_id,
              (int)t->cur_midi, t->current.frequency_hz,
              t->current.pitch_score, f->frame_id, t->start_sample,
              end_sample, f->first_sample + (uint64_t)f->n_fft, f->fs);
    t->state = NOTE_ST_IDLE;
    t->current.active = 0U;
    t->current.tracking_valid = 0U;
    t->cur_midi = -1;
    ClearCandidates(t);
    t->onset_pending = 0U;
    t->lost_count = 0U;
    t->quiet_count = 0U;
}

void NoteTrackerForceClose(NoteTracker *t, uint64_t end_sample,
                           uint8_t reason, uint8_t time_quality)
{
    NoteEvent ev;
    if ((t == 0) || (t->state != NOTE_ST_ACTIVE)) {
        if (t != 0) {
            t->state = NOTE_ST_IDLE;
            t->current.active = 0U;
            t->current.tracking_valid = 0U;
            t->cur_midi = -1;
            ClearCandidates(t);
            t->onset_pending = 0U;
        }
        return;
    }
    if (end_sample < t->start_sample) {
        end_sample = t->start_sample;
    }
    memset(&ev, 0, sizeof(ev));
    ev.schema_version = NOTE_SCHEMA_VERSION;
    ev.session_id = t->session_id;
    ev.event_seq = (t->queue != 0) ? (t->queue->pushed + 1U) : 0U;
    ev.type = (uint8_t)NOTE_EV_OFF;
    ev.reason = reason;
    ev.time_quality = time_quality;
    ev.note_id = t->cur_note_id;
    ev.midi = (uint8_t)((t->cur_midi < 0) ? 0 : t->cur_midi);
    ev.frequency_millihz = FreqMilliHz(t->current.frequency_hz);
    ev.pitch_score_milli = ScoreMilli(t->current.pitch_score);
    ev.frame_id = t->current.frame_id;
    ev.start_sample = t->start_sample;
    ev.end_sample = end_sample;
    ev.decision_sample = t->current.decision_sample;
    ev.fs = NOTE_FS_DEFAULT;
    if (t->queue != 0) {
        (void)NoteEventQueuePush(t->queue, &ev);
    }
    t->state = NOTE_ST_IDLE;
    t->current.active = 0U;
    t->current.tracking_valid = 0U;
    t->cur_midi = -1;
    ClearCandidates(t);
    t->onset_pending = 0U;
}

void NoteTrackerReset(NoteTracker *t, uint32_t session_id)
{
    NoteEventQueue *q;
    NoteConfig cfg;
    if (t == 0) {
        return;
    }
    q = t->queue;
    cfg = t->cfg;
    memset(t, 0, sizeof(*t));
    t->queue = q;
    t->cfg = cfg;
    t->session_id = session_id;
    t->next_note_id = 1U;
    t->cur_midi = -1;
    t->cand_midi = -1;
    t->change_midi = -1;
    t->state = NOTE_ST_IDLE;
    t->current.session_id = session_id;
}

void NoteTrackerInit(NoteTracker *t, NoteEventQueue *q,
                     const NoteConfig *cfg, uint32_t session_id)
{
    if (t == 0) {
        return;
    }
    memset(t, 0, sizeof(*t));
    t->queue = q;
    t->cfg = (cfg != 0) ? *cfg : (NoteConfig){0};
    if (cfg == 0) {
        NoteDefaultConfig(&t->cfg);
    }
    t->cfg.session_id = session_id;
    t->session_id = session_id;
    t->next_note_id = 1U;
    t->cur_midi = -1;
    t->cand_midi = -1;
    t->change_midi = -1;
    t->state = NOTE_ST_IDLE;
    t->current.session_id = session_id;
}

static int ReattackEvidence(const NoteTracker *t, const OnsetResult *onset)
{
    float min_recent;
    if ((onset == 0) || (onset->valid == 0U)) {
        return 0;
    }
    min_recent = MinRecentLevel(t);
    if (onset->level_db >= (onset->level_db_before + t->cfg.reattack_db)) {
        return 1;
    }
    if ((t->level_count > 0U) &&
        ((onset->level_db_before - min_recent) >= t->cfg.reattack_dip_db)) {
        return 1;
    }
    return 0;
}

static uint64_t PickOnsetBoundary(const NoteTracker *t, const AudioNoteFrame *f,
                                  uint64_t fallback, uint64_t low)
{
    uint64_t feature = f->first_sample + (uint64_t)(f->n_fft / 2U);
    uint64_t b = fallback;
    if (t->onset_pending != 0U) {
        if ((t->onset_sample >= low) &&
            (t->onset_sample <= feature) &&
            ((feature - t->onset_sample) <= (uint64_t)t->cfg.onset_association_samples)) {
            b = t->onset_sample;
        }
    }
    return ClampSample(b, low, feature);
}

void NoteTrackerProcess(NoteTracker *t, const AudioNoteFrame *f,
                        const OnsetResult *onset)
{
    uint64_t feature;
    uint64_t window_end;

    if ((t == 0) || (f == 0)) {
        return;
    }
    feature = f->first_sample + (uint64_t)(f->n_fft / 2U);
    window_end = f->first_sample + (uint64_t)f->n_fft;

    /* 1. Broken or discontinuous data: close and start a new segment. */
    if ((f->packet_valid == 0U) || (f->missing_frames > 0U)) {
        uint64_t end = t->last_valid_sample;
        if (t->have_last_frame != 0U) {
            end = t->last_valid_sample + (uint64_t)f->hop;
        }
        EmitOff(t, f, end, (uint8_t)NOTE_REASON_DATA_GAP,
                (uint8_t)NOTE_TQ_TRUNCATED);
        {
            NoteEvent ev;
            memset(&ev, 0, sizeof(ev));
            ev.schema_version = NOTE_SCHEMA_VERSION;
            ev.session_id = t->session_id;
            ev.event_seq = (t->queue != 0) ? (t->queue->pushed + 1U) : 0U;
            ev.type = (uint8_t)NOTE_EV_STREAM_GAP;
            ev.reason = (uint8_t)NOTE_REASON_DATA_GAP;
            ev.time_quality = (uint8_t)NOTE_TQ_TRUNCATED;
            ev.frame_id = f->frame_id;
            ev.start_sample = t->last_valid_sample;
            ev.end_sample = t->last_valid_sample;
            ev.decision_sample = (t->current.decision_sample != 0U)
                                     ? t->current.decision_sample : window_end;
            ev.fs = f->fs;
            if (t->queue != 0) {
                (void)NoteEventQueuePush(t->queue, &ev);
            }
        }
        ClearCandidates(t);
        t->onset_pending = 0U;
        t->lost_count = 0U;
        t->quiet_count = 0U;
        t->level_count = 0U;
        t->level_pos = 0U;
        t->have_last_frame = 0U;
        t->state = NOTE_ST_IDLE;
        t->current.active = 0U;
        t->current.tracking_valid = 0U;
        return;
    }

    /* 2. A fresh onset becomes a pending association candidate. */
    if ((onset != 0) && (onset->valid != 0U)) {
        if (t->onset_pending != 0U) {
            t->unassigned_onsets++;
        }
        t->onset_pending = 1U;
        t->onset_sample = onset->onset_sample;
        t->onset_deadline = onset->onset_sample +
                            (uint64_t)t->cfg.onset_association_samples;
        t->onset_level_before = onset->level_db_before;
        t->onset_strength = onset->strength;
    }

    /* 3. Pitch invalid: quiet release and pitch-lost are different paths. */
    if (f->pitch_valid == 0U) {
        t->current.tracking_valid = 0U;
        if (t->state == NOTE_ST_CANDIDATE) {
            ClearCandidates(t);
            t->state = NOTE_ST_IDLE;
        }
        if (f->signal_quiet != 0U) {
            t->lost_count = 0U;
            if (t->quiet_count == 0U) {
                t->first_quiet_sample = feature;
            }
            if (t->quiet_count < 255U) {
                t->quiet_count++;
            }
            if ((t->state == NOTE_ST_ACTIVE) &&
                (t->quiet_count >= t->cfg.quiet_release_frames)) {
                EmitOff(t, f, t->first_quiet_sample,
                        (uint8_t)NOTE_REASON_QUIET,
                        (uint8_t)NOTE_TQ_WINDOW_ESTIMATE);
            }
        } else {
            t->quiet_count = 0U;
            if (t->lost_count < 255U) {
                t->lost_count++;
            }
            if ((t->state == NOTE_ST_ACTIVE) &&
                (t->lost_count >= t->cfg.pitch_lost_frames)) {
                EmitOff(t, f, t->last_valid_sample,
                        (uint8_t)NOTE_REASON_PITCH_LOST,
                        (uint8_t)NOTE_TQ_TRUNCATED);
            }
        }
        if (onset != 0) {
            PushLevel(t, onset->level_db);
        }
        if (t->onset_pending != 0U) {
            if (feature > t->onset_deadline) {
                t->unassigned_onsets++;
                t->onset_pending = 0U;
            }
        }
        t->last_frame = f->frame_id;
        t->last_first_sample = f->first_sample;
        t->have_last_frame = 1U;
        return;
    }

    /* 4. Valid pitch. */
    t->lost_count = 0U;
    t->quiet_count = 0U;

    if (t->state == NOTE_ST_IDLE) {
        t->cand_midi = f->midi;
        t->cand_count = 1U;
        t->cand_start_sample = feature;
        t->cand_frame = f->frame_id;
        t->cand_first_sample = f->first_sample;
        t->state = NOTE_ST_CANDIDATE;
        UpdateCurrent(t, f, f->midi, f->frequency_hz, f->pitch_score,
                      (uint8_t)NOTE_TQ_WINDOW_ESTIMATE);
        t->current.active = 0U;
    } else if (t->state == NOTE_ST_CANDIDATE) {
        if (FrameContinuous(t, f, t->cand_frame, t->cand_first_sample) &&
            (f->midi == t->cand_midi)) {
            if (t->cand_count < 255U) {
                t->cand_count++;
            }
        } else {
            t->cand_midi = f->midi;
            t->cand_count = 1U;
            t->cand_start_sample = feature;
            t->cand_frame = f->frame_id;
            t->cand_first_sample = f->first_sample;
        }
        if ((t->cand_count >= t->cfg.start_confirm_frames) &&
            (f->pitch_score >= t->cfg.yin_min_score)) {
            uint64_t boundary = PickOnsetBoundary(t, f, t->cand_start_sample,
                                                  t->cand_start_sample);
            uint8_t tq = (boundary == t->cand_start_sample)
                             ? (uint8_t)NOTE_TQ_WINDOW_ESTIMATE
                             : (uint8_t)NOTE_TQ_ONSET_ESTIMATE;
            EmitOn(t, f, f->midi, f->frequency_hz, f->pitch_score,
                   boundary, window_end, (uint8_t)NOTE_REASON_START, tq);
            t->onset_pending = 0U;
            ClearCandidates(t);
        }
    } else { /* ACTIVE */
        if (f->midi == t->cur_midi) {
            uint64_t feature_now = feature;
            if (t->change_count > 0U) {
                t->jitter_suppressed++;
                ClearCandidates(t);
            }
            t->last_valid_sample = feature_now;
            t->current.frequency_hz = f->frequency_hz;
            t->current.pitch_score = f->pitch_score;
            t->current.frame_id = f->frame_id;
            t->current.feature_sample = feature_now;
            t->current.decision_sample = window_end;
            t->current.tracking_valid = 1U;
            t->current.active = 1U;

            if ((t->onset_pending != 0U) &&
                ReattackEvidence(t, onset) &&
                ((feature_now - t->start_sample) >=
                 (uint64_t)t->cfg.repeat_min_interval_samples) &&
                (t->onset_sample >= t->start_sample)) {
                uint64_t boundary = ClampSample(t->onset_sample,
                                                t->start_sample, feature_now);
                int16_t old_midi = t->cur_midi;
                EmitOff(t, f, boundary, (uint8_t)NOTE_REASON_REATTACK,
                        (uint8_t)NOTE_TQ_ONSET_ESTIMATE);
                EmitOn(t, f, (int)old_midi, f->frequency_hz,
                       f->pitch_score, boundary, window_end,
                       (uint8_t)NOTE_REASON_REATTACK,
                       (uint8_t)NOTE_TQ_ONSET_ESTIMATE);
                t->reattack_count++;
                t->onset_pending = 0U;
            }
        } else {
            /* A different pitch: short confirmation before switching. */
            if (FrameContinuous(t, f, t->change_frame, t->change_first_sample) &&
                (f->midi == t->change_midi)) {
                if (t->change_count < 255U) {
                    t->change_count++;
                }
            } else {
                t->change_midi = f->midi;
                t->change_count = 1U;
                t->change_first_sample = f->first_sample;
                t->change_frame = f->frame_id;
                t->change_feature_sample = feature;
            }
            if ((t->change_count >= t->cfg.change_confirm_frames) &&
                (f->pitch_score >= t->cfg.yin_min_score)) {
                uint64_t boundary = PickOnsetBoundary(t, f,
                                                      t->change_feature_sample,
                                                      t->start_sample);
                uint8_t tq = ((t->onset_pending != 0U) &&
                              (boundary == t->onset_sample))
                                 ? (uint8_t)NOTE_TQ_ONSET_ESTIMATE
                                 : (uint8_t)NOTE_TQ_WINDOW_ESTIMATE;
                EmitOff(t, f, boundary, (uint8_t)NOTE_REASON_CHANGE, tq);
                EmitOn(t, f, f->midi, f->frequency_hz, f->pitch_score,
                       boundary, window_end, (uint8_t)NOTE_REASON_CHANGE, tq);
                t->onset_pending = 0U;
                ClearCandidates(t);
            }
            t->current.tracking_valid = 0U;
        }
    }

    if (onset != 0) {
        PushLevel(t, onset->level_db);
    }

    /* 5. Pending onset that never found a pitch confirmation is not a note. */
    if (t->onset_pending != 0U) {
        if (feature > t->onset_deadline) {
            t->unassigned_onsets++;
            t->onset_pending = 0U;
        }
    }

    t->last_frame = f->frame_id;
    t->last_first_sample = f->first_sample;
    t->have_last_frame = 1U;
}

void NoteTrackerGetCurrent(const NoteTracker *t, NoteCurrent *out)
{
    if ((t == 0) || (out == 0)) {
        return;
    }
    *out = t->current;
}

const char *NoteTrackerStateName(const NoteTracker *t)
{
    if (t == 0) {
        return "?";
    }
    switch (t->state) {
    case NOTE_ST_IDLE: return "IDLE";
    case NOTE_ST_CANDIDATE: return "CAND";
    case NOTE_ST_ACTIVE: return "ACTIVE";
    default: return "?";
    }
}

const char *NoteReasonName(uint8_t reason)
{
    switch (reason) {
    case NOTE_REASON_START: return "START";
    case NOTE_REASON_CHANGE: return "CHANGE";
    case NOTE_REASON_REATTACK: return "REATTACK";
    case NOTE_REASON_QUIET: return "QUIET";
    case NOTE_REASON_PITCH_LOST: return "PITCH_LOST";
    case NOTE_REASON_DATA_GAP: return "DATA_GAP";
    case NOTE_REASON_STOP: return "STOP";
    case NOTE_REASON_QUEUE_OVERFLOW: return "QUEUE_OVERFLOW";
    default: return "?";
    }
}

const char *NoteEventTypeName(uint8_t type)
{
    switch (type) {
    case NOTE_EV_ON: return "ON";
    case NOTE_EV_OFF: return "OFF";
    case NOTE_EV_STREAM_GAP: return "GAP";
    case NOTE_EV_RESYNC: return "RESYNC";
    default: return "?";
    }
}
