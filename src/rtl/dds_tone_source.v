`timescale 1ns / 1ps
`default_nettype none

// DDS tone source (TEMPORARY test audio source).
//
// Generates a fixed-frequency sine at a configurable sample rate, to feed
// audio_fft_top while the real FIR/I2S front-end is not ready yet.
//
// HOW IT WORKS
//   The module runs on clk (100 MHz). Real audio arrives at SAMPLE_RATE_HZ
//   (16 kHz), so a counter produces a "sample tick" every
//   CLK_DIV = CLK_FREQ / SAMPLE_RATE clock cycles. On each tick the phase
//   accumulator advances by PHASE_INC, and a quarter-wave sine LUT (with
//   symmetry) produces the corresponding 16-bit signed sample.
//
// HOW TO CHANGE THE TONE FREQUENCY
//   The tone is set by PHASE_INC:
//       PHASE_INC = FREQ_HZ * 2^PHASE_WIDTH / SAMPLE_RATE_HZ
//   For 440 Hz @ 16 kHz, PHASE_WIDTH = 16:
//       PHASE_INC = 440 * 65536 / 16000 = 1802.24  ->  1802
//   To use another frequency, recompute PHASE_INC and edit the parameter
//   below. A small rounding error is fine: the FFT peak still lands on the
//   nearest bin.
//
// HOW TO CHANGE THE AMPLITUDE
//   The LUT is full scale (peak = 32767). To lower the amplitude, right-shift
//   the output, e.g. assign sample_data <= sine_w >>> 1 to halve it.
//
// HOW TO SWAP IN THE REAL FRONT-END
//   Delete the u_dds instantiation in system_top and connect your FIR/I2S
//   front-end instead. It only needs to drive:
//       sample_data  : signed 16-bit sample
//       sample_valid : 1-cycle pulse per sample (at 16 kHz)
//   (This source ignores sample_ready and free-runs; the frame controller
//    drops samples between frames, which is fine for a pure tone.)

module dds_tone_source #(
    parameter integer CLK_DIV     = 3125,  // 100 MHz / 16 kHz = 6250
    parameter integer PHASE_WIDTH = 16,
    parameter integer PHASE_INC   = 2048   // 440 Hz @ 16 kHz
) (
    input  wire               clk,
    input  wire               rst_n,

    output reg  signed [15:0] sample_data,
    output reg                sample_valid
);

    // ---- 16 kHz sample tick (one pulse every CLK_DIV clock cycles) ----
    reg [12:0] div_cnt;
    wire       tick;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            div_cnt <= 13'd0;
        else if (div_cnt == CLK_DIV - 1)
            div_cnt <= 13'd0;
        else
            div_cnt <= div_cnt + 1'b1;
    end
    assign tick = (div_cnt == CLK_DIV - 1);

    // ---- Phase accumulator ----
    reg [PHASE_WIDTH-1:0] phase;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            phase <= {PHASE_WIDTH{1'b0}};
        else if (tick)
            phase <= phase + PHASE_INC;
    end

    // ---- Quarter-wave LUT + symmetry ----
    // phase[15]   = sign (1 = negative half)
    // phase[14]   = reverse index (1 = use 63-index)
    // phase[13:8] = 6-bit index into the 64-entry quarter-wave table
    wire [5:0] idx_raw = phase[13:8];
    wire       rev     = phase[14];
    wire       neg     = phase[15];
    wire [5:0] idx     = rev ? (6'd63 - idx_raw) : idx_raw;

    reg signed [15:0] lut_out;
    always @(*) begin
        case (idx)
            6'd0 : lut_out = 16'sd0;      6'd1 : lut_out = 16'sd804;
            6'd2 : lut_out = 16'sd1608;   6'd3 : lut_out = 16'sd2411;
            6'd4 : lut_out = 16'sd3212;   6'd5 : lut_out = 16'sd4011;
            6'd6 : lut_out = 16'sd4808;   6'd7 : lut_out = 16'sd5602;
            6'd8 : lut_out = 16'sd6393;   6'd9 : lut_out = 16'sd7180;
            6'd10: lut_out = 16'sd7962;   6'd11: lut_out = 16'sd8739;
            6'd12: lut_out = 16'sd9512;   6'd13: lut_out = 16'sd10279;
            6'd14: lut_out = 16'sd11039;  6'd15: lut_out = 16'sd11793;
            6'd16: lut_out = 16'sd12540;  6'd17: lut_out = 16'sd13278;
            6'd18: lut_out = 16'sd14009;  6'd19: lut_out = 16'sd14731;
            6'd20: lut_out = 16'sd15446;  6'd21: lut_out = 16'sd16151;
            6'd22: lut_out = 16'sd16845;  6'd23: lut_out = 16'sd17529;
            6'd24: lut_out = 16'sd18204;  6'd25: lut_out = 16'sd18867;
            6'd26: lut_out = 16'sd19520;  6'd27: lut_out = 16'sd20160;
            6'd28: lut_out = 16'sd20787;  6'd29: lut_out = 16'sd21403;
            6'd30: lut_out = 16'sd22005;  6'd31: lut_out = 16'sd22594;
            6'd32: lut_out = 16'sd23170;  6'd33: lut_out = 16'sd23732;
            6'd34: lut_out = 16'sd24279;  6'd35: lut_out = 16'sd24812;
            6'd36: lut_out = 16'sd25329;  6'd37: lut_out = 16'sd25832;
            6'd38: lut_out = 16'sd26318;  6'd39: lut_out = 16'sd26789;
            6'd40: lut_out = 16'sd27244;  6'd41: lut_out = 16'sd27683;
            6'd42: lut_out = 16'sd28104;  6'd43: lut_out = 16'sd28509;
            6'd44: lut_out = 16'sd28897;  6'd45: lut_out = 16'sd29267;
            6'd46: lut_out = 16'sd29620;  6'd47: lut_out = 16'sd29955;
            6'd48: lut_out = 16'sd30272;  6'd49: lut_out = 16'sd30571;
            6'd50: lut_out = 16'sd30851;  6'd51: lut_out = 16'sd31113;
            6'd52: lut_out = 16'sd31356;  6'd53: lut_out = 16'sd31580;
            6'd54: lut_out = 16'sd31784;  6'd55: lut_out = 16'sd31970;
            6'd56: lut_out = 16'sd32137;  6'd57: lut_out = 16'sd32284;
            6'd58: lut_out = 16'sd32412;  6'd59: lut_out = 16'sd32520;
            6'd60: lut_out = 16'sd32609;  6'd61: lut_out = 16'sd32678;
            6'd62: lut_out = 16'sd32727;  6'd63: lut_out = 16'sd32755;
            default: lut_out = 16'sd0;
        endcase
    end

    wire signed [15:0] sine_w = neg ? -lut_out : lut_out;

    // ---- Output register ----
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sample_data  <= 16'sd0;
            sample_valid <= 1'b0;
        end else begin
            sample_valid <= tick;
            if (tick)
                sample_data <= sine_w;
        end
    end

endmodule

`default_nettype wire
