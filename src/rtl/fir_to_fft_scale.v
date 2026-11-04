`timescale 1ns / 1ps
`default_nettype none

// 24-bit FIR output -> 16-bit signed sample for FFT chain.
//
// Actual generated FIR: signed 24-bit input, signed integer 16-bit coefficients,
// 40-bit accumulator, Truncate_LSBs to 24-bit output (discard 16 accumulator LSBs).
// Input PCM is shifted left by 8 in fir_audio; selecting [23:8] below gives
// approximately sum(PCM[n-k] * coefficient[k]) >>> 16, NOT a unity-gain promise.
// Non-blocking FIR output cannot be stalled by FFT. Observe frame diagnostics
// for in-frame drops and intentional frame-gap omissions separately.
module fir_to_fft_scale (
    input  wire [23:0] s_tdata,
    input  wire        s_tvalid,

    output wire signed [15:0] m_tdata,
    output wire        m_tvalid
);

    assign m_tdata  = s_tdata[23:8];   // 24bit -> 16bit, take high 16 bits
    assign m_tvalid = s_tvalid;

endmodule

`default_nettype wire
