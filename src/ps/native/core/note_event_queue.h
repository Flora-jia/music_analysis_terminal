/* note_event_queue.h - bounded, non-blocking event queue (no malloc). */
#ifndef NOTE_EVENT_QUEUE_H
#define NOTE_EVENT_QUEUE_H

#include "audio_note_types.h"

typedef struct {
    NoteEvent items[NOTE_QUEUE_CAP];
    uint8_t   head;
    uint8_t   tail;
    uint8_t   count;
    uint8_t   resync_pending;
    uint32_t  pushed;
    uint32_t  popped;
    uint32_t  overflow;
} NoteEventQueue;

void NoteEventQueueInit(NoteEventQueue *q);

/* Returns 1 when stored, 0 when full (new event dropped, overflow counted,
 * resync requested). Never blocks and never overwrites queued events. */
int NoteEventQueuePush(NoteEventQueue *q, const NoteEvent *ev);

/* Returns 1 when an event was popped, 0 when empty. */
int NoteEventQueuePop(NoteEventQueue *q, NoteEvent *ev);

/* Returns 1 once if a resync marker is owed after overflow, then clears it. */
int NoteEventQueueTakeResync(NoteEventQueue *q);

uint32_t NoteEventQueueOverflowCount(const NoteEventQueue *q);

#endif /* NOTE_EVENT_QUEUE_H */
