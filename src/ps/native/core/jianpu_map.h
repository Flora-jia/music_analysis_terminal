/* jianpu_map.h - MIDI -> C-key jianpu digit / accidental / octave. */
#ifndef JIANPU_MAP_H
#define JIANPU_MAP_H

#include <stdint.h>

typedef struct {
    char    digit;          /* '1'..'7' */
    char    accidental;     /* 0 or '#' */
    int8_t  octave_offset;  /* relative to C4: C4=0, C3=-1, C5=+1 */
    char    name[6];        /* "C4", "F#4", ... or "-" when invalid */
} JianpuNote;

/* Returns 1 on valid MIDI 0..127, 0 otherwise (out is set to safe defaults). */
int JianpuFromMidi(int midi, JianpuNote *out);

#endif /* JIANPU_MAP_H */
