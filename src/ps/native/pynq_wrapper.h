/* pynq_wrapper.h - thin, stable C ABI for the PYNQ/Linux note engine.
 *
 * Wraps pitch_compare + onset_detector + note_tracker + note_event_queue +
 * jianpu_map behind a small set of functions Python can drive via ctypes.
 * Pure C99, no Xilinx headers, no malloc, no I/O.
 *
 * The board-only glue (XTime/xil_printf) from note_event_adapter.c is NOT
 * compiled here; this wrapper re-implements only that glue's logic portably.
 * Algorithm modules stay byte-identical to the verified baseline.
 */
#ifndef PYNW_WRAPPER_H
#define PYNW_WRAPPER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MP_BINS 2049

/* Current-note snapshot for the display (feeds update_note). */
typedef struct {
    int32_t  valid;           /* 1 = open note with valid pitch tracking */
    int32_t  active;          /* 1 = tracker has an open note */
    int32_t  tracking_valid;  /* 1 = pitch tracking currently valid */
    int32_t  midi;            /* -1 when no valid pitch */
    float    frequency_hz;
    float    confidence;      /* YinFFT score 0..1 */
    uint32_t note_id;
    int32_t  reason;          /* NoteReason */
    int32_t  time_quality;    /* NoteTimeQuality */
    uint32_t frame_id;
    uint64_t feature_sample;  /* display "updated_sample" */
    uint64_t decision_sample;
} MPResult;

/* One note event for the display (feeds commit_note). */
typedef struct {
    int32_t  type;            /* 1=ON 2=OFF 3=STREAM_GAP 4=RESYNC */
    uint32_t note_id;
    int32_t  midi;
    float    frequency_hz;
    float    confidence;
    uint64_t start_sample;
    uint64_t end_sample;      /* 0 while ON is open */
    float    duration_s;      /* (end-start)/fs; 0 while open */
    int32_t  reason;
    int32_t  time_quality;
    uint32_t frame_id;
    uint32_t session_id;
    uint32_t event_seq;
    uint32_t schema_version;
    uint32_t flags;
    uint64_t decision_sample;
    uint32_t fs;
} MPEvent;

/* Counters / status for the status page (feeds update_status). */
typedef struct {
    uint32_t on_count;
    uint32_t off_count;
    uint32_t onset_count;
    uint32_t unassigned_onsets;
    uint32_t bad_packet_count;
    uint32_t gap_count;
    uint32_t event_overflow;
    int32_t  noise_db_milli;   /* calibrated noise floor, 0 when uncalibrated */
    int32_t  calibrated;       /* 1 = noise floor from a real calibration */
    int32_t  state;            /* 0 IDLE 1 CANDIDATE 2 ACTIVE */
} MPSummary;

/* C-key jianpu fields for a MIDI note. */
typedef struct {
    int32_t valid;             /* 1 = midi was 0..127 */
    int32_t degree;            /* 1..7 (jianpu digit), 0 when invalid */
    int32_t accidental;        /* 0 none, 1 sharp (this build has no flat) */
    int32_t octave_offset;     /* relative to C4: C4=0, C5=+1 */
    char    name[8];           /* "C4", "F#4", ... or "-" */
} MPJianpu;

uint32_t mp_abi_version(void);
uint32_t mp_sizeof(uint32_t type_id);
uint32_t mp_offsetof(uint32_t type_id, uint32_t field_id);
int mp_reset_checked(uint32_t session_id);
int mp_watchdog(void);
int  mp_init(uint32_t session_id);
void mp_reset(uint32_t session_id);

/* Feed one 2049-bin magnitude frame. mag is 2049 uint16 linear magnitudes,
 * bin k = k * (16000/4096) Hz. Runs YinFFT + onset + note state machine.
 * Returns 0 on success, -1 on bad args / not initialized. */
int  mp_process(const uint16_t *mag, int bins, uint64_t first_sample,
                uint32_t frame_id, uint32_t gap, MPResult *out);

/* Signal a validated-packet failure: closes any open note as DATA_GAP. */
int  mp_on_bad_packet(uint32_t frame_id, int check_code);

/* Drain one event. Returns 1 when *out holds an event, 0 when empty. */
int  mp_pop_event(MPEvent *out);

/* Returns 1 once if a resync marker is owed after queue overflow. */
int  mp_take_resync(void);

/* Force-close any open note as STOP/TRUNCATED (shutdown / DMA stop). */
int  mp_stop(void);

/* Noise-floor calibration (call during a silent interval). */
int  mp_calib_start(void);
int  mp_calib_ready(void);

int  mp_jianpu(int midi, MPJianpu *out);
int  mp_get_summary(MPSummary *out);

const char *mp_version(void);

#ifdef __cplusplus
}
#endif

#endif /* PYNW_WRAPPER_H */
