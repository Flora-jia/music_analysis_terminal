`timescale 1ns / 1ps
`default_nettype none

// Auto-trigger for the FFT chain.
// Fires one start_pulse after reset, then re-triggers on every result_valid.
//
// NOTE: must re-trigger on result_valid (NOT frame_done). The peak search is
// still busy processing the previous frame's FFT output when frame_done fires;
// a trigger at that moment is silently dropped and the chain stalls. Waiting
// for result_valid guarantees the whole chain is idle before the next frame.

module frame_auto_trigger #(
    parameter integer INIT_DELAY = 256   // clock cycles after reset before first trigger
) (
    input  wire clk,
    input  wire rst_n,

    input  wire result_valid,   // one-cycle pulse at end of each frame
    output reg  start_pulse     // one-cycle pulse to start a frame
);

    reg [15:0] cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            start_pulse <= 1'b0;
            cnt         <= 16'd0;
        end else begin
            start_pulse <= 1'b0;
            if (cnt < INIT_DELAY) begin
                cnt <= cnt + 1'b1;
                if (cnt == INIT_DELAY - 1)
                    start_pulse <= 1'b1;        // first frame
            end else if (result_valid) begin
                start_pulse <= 1'b1;            // re-trigger after each frame
            end
        end
    end

endmodule

`default_nettype wire
