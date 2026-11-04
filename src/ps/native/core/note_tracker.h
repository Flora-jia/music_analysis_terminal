/* note_tracker.h - IDLE/CANDIDATE/ACTIVE note state machine.
 *
 * Consumes one AudioNoteFrame plus the OnsetResult of the same frame and
 * emits NOTE_ON/NOTE_OFF into a bounded queue. No drivers, no allocation.
 */
#ifndef NOTE_TRACKER_H
#define NOTE_TRACKER_H

#include "audio_note_types.h"
#include "note_event_queue.h"
#include "onset_detector.h"

typedef enum {
    NOTE_ST_IDLE = 0,
    NOTE_ST_CANDIDATE = 1,
    NOTE_ST_ACTIVE = 2
} NoteTrackerState;

typedef struct {
    NoteConfig      cfg;
    NoteEventQueue *queue;
    NoteTrackerState state;

    uint32_t session_id;
    uint32_t next_note_id;
    uint32_t cur_note_id;
    int16_t  cur_midi;
    uint64_t start_sample;
    uint64_t last_valid_sample;
    uint64_t last_feature_sample;
    uint32_t last_frame;
    uint64_t last_first_sample;
    uint8_t  have_last_frame;

    int16_t  cand_midi;
    uint8_t  cand_count;
    uint64_t cand_start_sample;
    uint32_t cand_frame;
    uint64_t cand_first_sample;

    int16_t  change_midi;
    uint8_t  change_count;
    uint64_t change_first_sample;
    uint32_t change_frame;
    uint64_t change_feature_sample;

    uint8_t  lost_count;
    uint8_t  quiet_count;
    uint64_t first_quiet_sample;

    /* One pending onset waiting for pitch confirmation. */
    uint8_t  onset_pending;
    uint64_t onset_sample;
    uint64_t onset_deadline;
    float    onset_level_before;
    float    onset_strength;

    /* Recent level history, for REATTACK evidence (8 frames = 256 ms). */
    float    level_recent[8];
    uint8_t  level_count;
    uint8_t  level_pos;

    NoteCurrent current;

    uint32_t unassigned_onsets;
    uint32_t reattack_count;
    uint32_t jitter_suppressed;
} NoteTracker;

void NoteTrackerInit(NoteTracker *t, NoteEventQueue *q,
                     const NoteConfig *cfg, uint32_t session_id);
void NoteTrackerReset(NoteTracker *t, uint32_t session_id);
void NoteTrackerProcess(NoteTracker *t, const AudioNoteFrame *f,
                        const OnsetResult *onset);
void NoteTrackerForceClose(NoteTracker *t, uint64_t end_sample,
                           uint8_t reason, uint8_t time_quality);
void NoteTrackerGetCurrent(const NoteTracker *t, NoteCurrent *out);
const char *NoteTrackerStateName(const NoteTracker *t);
const char *NoteReasonName(uint8_t reason);
const char *NoteEventTypeName(uint8_t type);

#endif /* NOTE_TRACKER_H */
