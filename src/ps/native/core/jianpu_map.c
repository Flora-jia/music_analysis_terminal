/* jianpu_map.c - first-round C-key mapping; enharmonic spelling is not inferred. */
#include "jianpu_map.h"

static const char degree_table[12] = {
    '1', '1', '2', '2', '3', '4', '4', '5', '5', '6', '6', '7'
};
static const char accidental_table[12] = {
    0, '#', 0, '#', 0, 0, '#', 0, '#', 0, '#', 0
};
static const char *name_table[12] = {
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
};

int JianpuFromMidi(int midi, JianpuNote *out)
{
    int pc;
    int octave;

    if (out == 0) {
        return 0;
    }
    out->digit = '-';
    out->accidental = 0;
    out->octave_offset = 0;
    out->name[0] = '-';
    out->name[1] = 0;

    if ((midi < 0) || (midi > 127)) {
        return 0;
    }
    pc = midi % 12;
    octave = midi / 12 - 1;
    out->digit = degree_table[pc];
    out->accidental = accidental_table[pc];
    out->octave_offset = (int8_t)(octave - 4); /* C4 = 0 */

    out->name[0] = name_table[pc][0];
    if (name_table[pc][1] != 0) {
        out->name[1] = name_table[pc][1];
        out->name[2] = (char)('0' + ((octave < 0) ? 0 : (octave % 10)));
        out->name[3] = 0;
    } else {
        out->name[1] = (char)('0' + ((octave < 0) ? 0 : (octave % 10)));
        out->name[2] = 0;
    }
    return 1;
}
