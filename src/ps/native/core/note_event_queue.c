/* note_event_queue.c - bounded ring buffer, 64 entries, no allocation. */
#include "note_event_queue.h"
#include <string.h>

void NoteEventQueueInit(NoteEventQueue *q)
{
    if (q == 0) {
        return;
    }
    memset(q, 0, sizeof(*q));
}

int NoteEventQueuePush(NoteEventQueue *q, const NoteEvent *ev)
{
    if ((q == 0) || (ev == 0)) {
        return 0;
    }
    if (q->count >= (uint8_t)NOTE_QUEUE_CAP) {
        q->overflow++;
        q->resync_pending = 1U;
        return 0;
    }
    q->items[q->tail] = *ev;
    q->tail = (uint8_t)((q->tail + 1U) % NOTE_QUEUE_CAP);
    q->count++;
    q->pushed++;
    return 1;
}

int NoteEventQueuePop(NoteEventQueue *q, NoteEvent *ev)
{
    if ((q == 0) || (ev == 0) || (q->count == 0U)) {
        return 0;
    }
    *ev = q->items[q->head];
    q->head = (uint8_t)((q->head + 1U) % NOTE_QUEUE_CAP);
    q->count--;
    q->popped++;
    return 1;
}

int NoteEventQueueTakeResync(NoteEventQueue *q)
{
    if ((q != 0) && (q->resync_pending != 0U)) {
        q->resync_pending = 0U;
        return 1;
    }
    return 0;
}

uint32_t NoteEventQueueOverflowCount(const NoteEventQueue *q)
{
    return (q != 0) ? q->overflow : 0U;
}
