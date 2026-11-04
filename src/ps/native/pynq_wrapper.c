/* pynq_wrapper.c - portable re-implementation of note_event_adapter.c's glue.
 *
 * The algorithm modules (pitch_compare, onset_detector, note_tracker,
 * note_event_queue, jianpu_map) are compiled verbatim from the verified
 * baseline. Only the board glue (XTime/xil_printf) is replaced here.
 *
 * One engine instance; no malloc; callers serialise access.
 */
#include "pynq_wrapper.h"
#include "pitch_compare.h"
#include "onset_detector.h"
#include "note_tracker.h"
#include "note_event_queue.h"
#include "jianpu_map.h"
#include "audio_note_types.h"

#include <string.h>
#include <stddef.h>

#define MP_VERSION "libmusic_ps 2.0.0"

/* ---- engine state (mirrors note_event_adapter.c globals) ---- */
static NoteConfig     g_cfg;
static PitchConfig    g_pitch_cfg;
static OnsetContext   g_onset;
static NoteTracker    g_tracker;
static NoteEventQueue g_queue;
static NoteCurrent    g_current;
static float          g_mag[NOTE_MAG_BINS];   /* 2049 linear magnitudes */

static uint32_t g_session = 1U;
static int      g_initialized = 0;
static int      g_bad_active = 0;
static int      g_have_good = 0;

/* ---- counters ---- */
static uint32_t g_on_count = 0U;
static uint32_t g_off_count = 0U;
static uint32_t g_onset_count = 0U;
static uint32_t g_bad_count = 0U;
static uint32_t g_gap_count = 0U;

const char *mp_version(void)
{
    return MP_VERSION;
}

int mp_init(uint32_t session_id)
{
    g_session = session_id;

    NoteDefaultConfig(&g_cfg);
    g_cfg.session_id = session_id;

    /* Match ComparePitch's runtime overrides (the values main.c ships with). */
    PitchDefaultConfig(&g_pitch_cfg);
    g_pitch_cfg.min_hz = 27.0f;
    g_pitch_cfg.max_hz = 4300.0f;
    g_pitch_cfg.min_peak = 20.0f;
    g_pitch_cfg.min_peak_median_ratio = 6.0f;
    g_pitch_cfg.yin_min_confidence = 0.8f;
    g_pitch_cfg.twm_max_error = 10.0f;
    g_pitch_cfg.twm_subharmonics = 0;
    g_pitch_cfg.yin_first_minimum = 1;

    PitchInit();
    OnsetInit(&g_onset, &g_cfg);
    NoteEventQueueInit(&g_queue);
    NoteTrackerInit(&g_tracker, &g_queue, &g_cfg, session_id);

    memset(&g_current, 0, sizeof(g_current));
    g_bad_active = 0;
    g_have_good = 0;
    g_on_count = g_off_count = g_onset_count = g_bad_count = g_gap_count = 0U;
    g_initialized = 1;
    return 0;
}

int mp_reset_checked(uint32_t session_id)
{
    if (g_initialized && (g_tracker.state == NOTE_ST_ACTIVE || g_queue.count || g_queue.resync_pending)) return -2;
    return mp_init(session_id);
}
void mp_reset(uint32_t session_id)
{
    (void)mp_reset_checked(session_id); /* Legacy call is now a guarded no-op on undelivered data. */
}

int mp_watchdog(void)
{
    if (!g_initialized) return -1;
    if (g_have_good && g_tracker.state == NOTE_ST_ACTIVE) {
        uint64_t end = g_tracker.last_valid_sample + (uint64_t)NOTE_HOP_DEFAULT;
        NoteTrackerForceClose(&g_tracker, end, (uint8_t)NOTE_REASON_STOP, (uint8_t)NOTE_TQ_TRUNCATED);
    }
    g_have_good = 0;
    return 0;
}

int mp_process(const uint16_t *mag, int bins, uint64_t first_sample,
               uint32_t frame_id, uint32_t gap, MPResult *out)
{
    PitchReport report;
    AudioNoteFrame f;
    OnsetResult onset;
    int k;

    if (!g_initialized || mag == 0 || bins < (int)NOTE_MAG_BINS) {
        return -1;
    }

    for (k = 0; k < (int)NOTE_MAG_BINS; ++k) {
        g_mag[k] = (float)mag[k];
    }

    /* ---- pitch (YinFFT only; the note layer consumes YinFFT) ---- */
    memset(&report, 0, sizeof(report));
    if (PitchPrepare(g_mag, &g_pitch_cfg, &report)) {
        PitchRunYinFFT(&g_pitch_cfg, &report.yinfft);
    } else {
        report.yinfft.valid = 0;
        report.yinfft.reason = report.gate_reason;
    }

    /* ---- build the frame exactly like NoteAdapterOnFrame ---- */
    memset(&f, 0, sizeof(f));
    f.first_sample = first_sample;
    f.frame_id = frame_id;
    f.fs = NOTE_FS_DEFAULT;
    f.n_fft = NOTE_NFFT_DEFAULT;
    f.hop = NOTE_HOP_DEFAULT;
    f.packet_valid = 1U;
    f.missing_frames = gap;

    if ((report.yinfft.valid != 0) &&
        (report.yinfft.frequency > 0.0f) &&
        (report.yinfft.frequency < 8000.0f) &&
        (report.yinfft.midi >= 0) && (report.yinfft.midi <= 127) &&
        (report.yinfft.score >= g_cfg.yin_min_score)) {
        f.pitch_valid = 1U;
        f.midi = (int16_t)report.yinfft.midi;
        f.frequency_hz = report.yinfft.frequency;
        f.pitch_score = report.yinfft.score;
    } else {
        f.pitch_valid = 0U;
        f.midi = -1;
        f.frequency_hz = 0.0f;
        f.pitch_score = report.yinfft.score;
    }

    OnsetProcess(&g_onset, &g_cfg, &f, g_mag, &onset);
    f.signal_quiet = onset.quiet;
    f.signal_audible = onset.audible;
    if (onset.valid != 0U) {
        g_onset_count++;
    }

    NoteTrackerProcess(&g_tracker, &f, &onset);

    if (gap > 0U) {
        g_gap_count++;
        OnsetReset(&g_onset);   /* never diff across missing time */
    }

    g_have_good = 1;
    g_bad_active = 0;
    NoteTrackerGetCurrent(&g_tracker, &g_current);

    if (out != 0) {
        memset(out, 0, sizeof(*out));
        out->valid = (g_current.active != 0 && g_current.tracking_valid != 0) ? 1 : 0;
        out->active = (g_current.active != 0) ? 1 : 0;
        out->tracking_valid = (g_current.tracking_valid != 0) ? 1 : 0;
        out->midi = out->valid ? (int32_t)g_current.midi : -1;
        out->frequency_hz = out->valid ? g_current.frequency_hz : 0.0f;
        out->confidence = g_current.pitch_score;
        out->note_id = out->valid ? g_current.note_id : 0U;
        out->reason = (int32_t)g_current.reason;
        out->time_quality = (int32_t)g_current.time_quality;
        out->frame_id = g_current.frame_id;
        out->feature_sample = g_current.feature_sample;
        out->decision_sample = g_current.decision_sample;
    }
    return 0;
}

int mp_on_bad_packet(uint32_t frame_id, int check_code)
{
    (void)check_code;
    if (!g_initialized) {
        return -1;
    }
    g_bad_count++;
    if (g_bad_active == 0) {
        AudioNoteFrame f;
        memset(&f, 0, sizeof(f));
        f.first_sample = 0U;
        f.frame_id = frame_id;
        f.fs = NOTE_FS_DEFAULT;
        f.n_fft = NOTE_NFFT_DEFAULT;
        f.hop = NOTE_HOP_DEFAULT;
        f.packet_valid = 0U;   /* closes an open note as DATA_GAP */
        f.missing_frames = 1U;
        f.midi = -1;
        NoteTrackerProcess(&g_tracker, &f, 0);
        OnsetReset(&g_onset);
        g_bad_active = 1;
        g_have_good = 0;
    }
    g_current.tracking_valid = 0U;
    g_tracker.current.tracking_valid = 0U;
    return 0;
}

int mp_pop_event(MPEvent *out)
{
    NoteEvent e;
    if (!g_initialized) {
        return 0;
    }
    if (!NoteEventQueuePop(&g_queue, &e)) {
        return 0;
    }

    if (e.type == NOTE_EV_ON) {
        g_on_count++;
    } else if (e.type == NOTE_EV_OFF) {
        g_off_count++;
    }

    if (out != 0) {
        memset(out, 0, sizeof(*out));
        out->type = (int32_t)e.type;
        out->note_id = e.note_id;
        out->midi = (int32_t)e.midi;
        out->frequency_hz = (float)e.frequency_millihz / 1000.0f;
        out->confidence = (float)e.pitch_score_milli / 1000.0f;
        out->start_sample = e.start_sample;
        out->end_sample = e.end_sample;
        out->duration_s = (e.type == NOTE_EV_OFF && e.end_sample >= e.start_sample)
                              ? (float)(e.end_sample - e.start_sample) / (float)e.fs
                              : 0.0f;
        out->reason = (int32_t)e.reason;
        out->time_quality = (int32_t)e.time_quality;
        out->frame_id = e.frame_id;
        out->session_id = e.session_id;
        out->event_seq = e.event_seq;
        out->schema_version = e.schema_version;
        out->flags = e.flags;
        out->decision_sample = e.decision_sample;
        out->fs = e.fs;
    }
    return 1;
}

int mp_take_resync(void)
{
    if (!g_initialized) {
        return 0;
    }
    return NoteEventQueueTakeResync(&g_queue);
}

int mp_stop(void)
{
    uint64_t end;
    if (!g_initialized) {
        return -1;
    }
    if (g_tracker.state != NOTE_ST_ACTIVE) {
        return 0;
    }
    end = g_tracker.last_valid_sample + (uint64_t)NOTE_HOP_DEFAULT;
    NoteTrackerForceClose(&g_tracker, end, (uint8_t)NOTE_REASON_STOP,
                          (uint8_t)NOTE_TQ_TRUNCATED);
    return 0;
}

int mp_calib_start(void)
{
    if (!g_initialized) {
        return -1;
    }
    OnsetCalibStart(&g_onset);
    return 0;
}

int mp_calib_ready(void)
{
    return OnsetCalibReady(&g_onset) != 0;
}

int mp_jianpu(int midi, MPJianpu *out)
{
    JianpuNote jp;
    int ok;
    size_t n;

    if (out == 0) {
        return 0;
    }
    memset(out, 0, sizeof(*out));
    ok = JianpuFromMidi(midi, &jp);
    if (!ok) {
        out->name[0] = '-';
        out->name[1] = '\0';
        return 0;
    }
    out->valid = 1;
    out->degree = (int32_t)(jp.digit - '0');   /* '1'..'7' -> 1..7 */
    out->accidental = (jp.accidental == '#') ? 1 : 0;
    out->octave_offset = (int32_t)jp.octave_offset;
    n = strlen(jp.name);
    if (n >= sizeof(out->name)) {
        n = sizeof(out->name) - 1U;
    }
    memcpy(out->name, jp.name, n);
    out->name[n] = '\0';
    return 1;
}

int mp_get_summary(MPSummary *out)
{
    if (out == 0 || !g_initialized) {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    out->on_count = g_on_count;
    out->off_count = g_off_count;
    out->onset_count = g_onset_count;
    out->unassigned_onsets = g_tracker.unassigned_onsets;
    out->bad_packet_count = g_bad_count;
    out->gap_count = g_gap_count;
    out->event_overflow = NoteEventQueueOverflowCount(&g_queue);
    out->noise_db_milli = OnsetCalibReady(&g_onset)
                              ? (int32_t)(OnsetNoiseDb(&g_onset) * 1000.0f) : 0;
    out->calibrated = OnsetCalibReady(&g_onset) ? 1 : 0;
    out->state = (int32_t)g_tracker.state;
    return 0;
}

uint32_t mp_abi_version(void) { return 2U; }
uint32_t mp_sizeof(uint32_t id) { switch(id) {case 1: return (uint32_t)sizeof(MPResult);case 2: return (uint32_t)sizeof(MPEvent);case 3: return (uint32_t)sizeof(MPSummary);case 4: return (uint32_t)sizeof(MPJianpu);default:return 0U;} }
uint32_t mp_offsetof(uint32_t id,uint32_t field) { switch(id) {case 1: { static const uint32_t x[]={offsetof(MPResult,valid),offsetof(MPResult,active),offsetof(MPResult,tracking_valid),offsetof(MPResult,midi),offsetof(MPResult,frequency_hz),offsetof(MPResult,confidence),offsetof(MPResult,note_id),offsetof(MPResult,reason),offsetof(MPResult,time_quality),offsetof(MPResult,frame_id),offsetof(MPResult,feature_sample),offsetof(MPResult,decision_sample)}; return field<12?x[field]:UINT32_MAX; }case 2: { static const uint32_t x[]={offsetof(MPEvent,type),offsetof(MPEvent,note_id),offsetof(MPEvent,midi),offsetof(MPEvent,frequency_hz),offsetof(MPEvent,confidence),offsetof(MPEvent,start_sample),offsetof(MPEvent,end_sample),offsetof(MPEvent,duration_s),offsetof(MPEvent,reason),offsetof(MPEvent,time_quality),offsetof(MPEvent,frame_id),offsetof(MPEvent,session_id),offsetof(MPEvent,event_seq),offsetof(MPEvent,schema_version),offsetof(MPEvent,flags),offsetof(MPEvent,decision_sample),offsetof(MPEvent,fs)}; return field<17?x[field]:UINT32_MAX; }case 3: { static const uint32_t x[]={offsetof(MPSummary,on_count),offsetof(MPSummary,off_count),offsetof(MPSummary,onset_count),offsetof(MPSummary,unassigned_onsets),offsetof(MPSummary,bad_packet_count),offsetof(MPSummary,gap_count),offsetof(MPSummary,event_overflow),offsetof(MPSummary,noise_db_milli),offsetof(MPSummary,calibrated),offsetof(MPSummary,state)}; return field<10?x[field]:UINT32_MAX; }case 4: { static const uint32_t x[]={offsetof(MPJianpu,valid),offsetof(MPJianpu,degree),offsetof(MPJianpu,accidental),offsetof(MPJianpu,octave_offset),offsetof(MPJianpu,name)}; return field<5?x[field]:UINT32_MAX; }default:return UINT32_MAX;} }
