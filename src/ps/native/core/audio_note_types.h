/* audio_note_types.h - shared types for PS note segmentation (stage A/B).
 *
 * Pure C99, no Xilinx headers, no malloc. Compiles on host and on Cortex-A9.
 * All time values are source sample indices (64-bit), never packet counts.
 */
#ifndef AUDIO_NOTE_TYPES_H
#define AUDIO_NOTE_TYPES_H

#include <stdint.h>

#define NOTE_SCHEMA_VERSION   1u
#define NOTE_FS_DEFAULT       16000u
#define NOTE_NFFT_DEFAULT     4096u
#define NOTE_HOP_DEFAULT      512u
#define NOTE_MAG_BINS         2049u
#define NOTE_QUEUE_CAP        64u

/* Event types. STREAM_GAP/RESYNC are control markers, not jianpu notes. */
typedef enum {
    NOTE_EV_NONE = 0,
    NOTE_EV_ON = 1,
    NOTE_EV_OFF = 2,
    NOTE_EV_STREAM_GAP = 3,
    NOTE_EV_RESYNC = 4
} NoteEventType;

typedef enum {
    NOTE_REASON_START = 0,
    NOTE_REASON_CHANGE = 1,
    NOTE_REASON_REATTACK = 2,
    NOTE_REASON_QUIET = 3,
    NOTE_REASON_PITCH_LOST = 4,
    NOTE_REASON_DATA_GAP = 5,
    NOTE_REASON_STOP = 6,
    NOTE_REASON_QUEUE_OVERFLOW = 7
} NoteReason;

typedef enum {
    NOTE_TQ_WINDOW_ESTIMATE = 0,
    NOTE_TQ_ONSET_ESTIMATE = 1,
    NOTE_TQ_TRUNCATED = 2
} NoteTimeQuality;

/* One analysed window handed to the note layer.
 * first_sample is the window start; feature_sample = first_sample + n_fft/2.
 * packet_valid=1 with pitch_valid=0 is legal (silence or unvoiced). */
typedef struct {
    uint64_t first_sample;
    uint32_t frame_id;
    uint32_t fs;
    uint16_t n_fft;
    uint16_t hop;
    uint8_t  packet_valid;
    uint32_t missing_frames;
    uint8_t  pitch_valid;
    int16_t  midi;
    float    frequency_hz;
    float    pitch_score;
    uint8_t  signal_quiet;   /* independent level decision, not "pitch invalid" */
    uint8_t  signal_audible; /* level above onset gate */
} AudioNoteFrame;

/* Formal event record. Serialise field by field; never dump the struct. */
typedef struct {
    uint32_t schema_version;
    uint32_t session_id;
    uint32_t event_seq;
    uint8_t  type;
    uint8_t  reason;
    uint8_t  time_quality;
    uint8_t  flags;          /* bit0: record incomplete (queue overflow) */
    uint32_t note_id;
    uint8_t  midi;
    uint8_t  reserved8;
    uint16_t reserved16;
    uint32_t frequency_millihz;
    int32_t  pitch_score_milli;
    uint32_t frame_id;
    uint64_t start_sample;
    uint64_t end_sample;     /* 0 while NOTE_ON is open, left-closed/right-open */
    uint64_t decision_sample;
    uint32_t fs;
} NoteEvent;

/* Frequently refreshed snapshot for display; separate from events. */
typedef struct {
    uint32_t session_id;
    uint32_t note_id;
    uint8_t  active;
    uint8_t  tracking_valid;
    uint8_t  midi;
    uint8_t  reason;
    uint8_t  time_quality;
    float    frequency_hz;
    float    pitch_score;
    uint32_t frame_id;
    uint64_t feature_sample;
    uint64_t decision_sample;
} NoteCurrent;

/* Tunables. Defaults are first-round values, not tuned conclusions. */
typedef struct {
    uint32_t session_id;
    uint8_t  start_confirm_frames;      /* 2 */
    uint8_t  change_confirm_frames;     /* 2 */
    uint8_t  quiet_release_frames;      /* 2 */
    uint8_t  pitch_lost_frames;         /* 3 */
    float    yin_min_score;             /* 0.80 */
    uint32_t onset_association_samples; /* 2048 = 128 ms */
    uint32_t repeat_min_interval_samples;/* 1536 = 96 ms */
    uint32_t stream_watchdog_us;        /* 128000 */

    /* onset feature band, first round bin 2..1280 */
    uint32_t onset_band_lo;
    uint32_t onset_band_hi;
    float    onset_aref;                /* 1.0 amplitude unit */
    uint8_t  onset_history_len;         /* 31 */
    float    onset_alpha;               /* 3.0 * MAD */
    float    onset_flux_floor;          /* absolute floor, calibrated later */
    float    onset_gate_db;             /* noise + 6 dB */
    float    onset_release_db;          /* noise + 3 dB */
    float    reattack_db;               /* +3 dB */
    float    reattack_dip_db;           /* prior 6 dB dip */
    uint8_t  onset_require_fall;        /* 1 */
    float    onset_fall_ratio;          /* 0.5 */
    uint8_t  onset_calib_frames;        /* 16 */
    float    fixed_quiet_db;            /* used only when uncalibrated */
} NoteConfig;

void NoteDefaultConfig(NoteConfig *c);

#endif /* AUDIO_NOTE_TYPES_H */
