`timescale 1ns/1ps
`default_nettype none

// FCLK-domain capture diagnostics. A snapshot remains visible until the next
// window ends; counts and peaks include transfers on the final window cycle.
// WINDOW_CYCLES=50,000,000 gives one second at the actual 50 MHz FCLK_CLK0.
// The FIR counter measures valid output beats; its non-blocking IP has no ready.
module audio_capture_debug #(
    parameter integer WINDOW_CYCLES = 50000000,
    parameter integer CLIP_LEVEL = 32760
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [2:0]  rx_tid,
    input  wire signed [15:0] raw_pcm,
    input  wire        rx_fire,
    input  wire        selected_pcm_fire,
    input  wire        fir_valid,
    output reg [31:0]  count0,
    output reg [31:0]  count1,
    output reg [31:0]  count_selected,
    output reg [31:0]  count_fir,
    output reg [15:0]  peak0,
    output reg [15:0]  peak1,
    output reg [31:0]  clip_count0,
    output reg [31:0]  clip_count1,
    output reg [31:0]  window_id,
    output reg         snapshot_valid
);
    reg [31:0] window_cycle;
    reg [31:0] running_count0, running_count1;
    reg [31:0] running_selected, running_fir;
    reg [15:0] running_peak0, running_peak1;
    reg [31:0] running_clip0, running_clip1;

    wire fire0 = rx_fire && (rx_tid == 3'd0);
    wire fire1 = rx_fire && (rx_tid == 3'd1);
    // Unsigned absolute value represents |-32768| exactly as 16'h8000.
    wire [15:0] pcm_abs = raw_pcm[15] ? (~raw_pcm + 16'd1) : raw_pcm;
    wire sample_clipped = (pcm_abs >= CLIP_LEVEL);
    wire [31:0] next_count0 = running_count0 + (fire0 ? 32'd1 : 32'd0);
    wire [31:0] next_count1 = running_count1 + (fire1 ? 32'd1 : 32'd0);
    wire [31:0] next_selected = running_selected + (selected_pcm_fire ? 32'd1 : 32'd0);
    wire [31:0] next_fir = running_fir + (fir_valid ? 32'd1 : 32'd0);
    wire [15:0] next_peak0 = (fire0 && pcm_abs > running_peak0) ? pcm_abs : running_peak0;
    wire [15:0] next_peak1 = (fire1 && pcm_abs > running_peak1) ? pcm_abs : running_peak1;
    wire [31:0] next_clip0 = running_clip0 + ((fire0 && sample_clipped) ? 32'd1 : 32'd0);
    wire [31:0] next_clip1 = running_clip1 + ((fire1 && sample_clipped) ? 32'd1 : 32'd0);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            window_cycle <= 32'd0;
            running_count0 <= 32'd0; running_count1 <= 32'd0;
            running_selected <= 32'd0; running_fir <= 32'd0;
            running_peak0 <= 16'd0; running_peak1 <= 16'd0;
            running_clip0 <= 32'd0; running_clip1 <= 32'd0;
            count0 <= 32'd0; count1 <= 32'd0;
            count_selected <= 32'd0; count_fir <= 32'd0;
            peak0 <= 16'd0; peak1 <= 16'd0;
            clip_count0 <= 32'd0; clip_count1 <= 32'd0;
            window_id <= 32'd0;
            snapshot_valid <= 1'b0;
        end else begin
            snapshot_valid <= 1'b0;
            if (window_cycle == WINDOW_CYCLES - 1) begin
                window_cycle <= 32'd0;
                count0 <= next_count0; count1 <= next_count1;
                count_selected <= next_selected; count_fir <= next_fir;
                peak0 <= next_peak0; peak1 <= next_peak1;
                clip_count0 <= next_clip0; clip_count1 <= next_clip1;
                window_id <= window_id + 1'b1;
                snapshot_valid <= 1'b1;
                running_count0 <= 32'd0; running_count1 <= 32'd0;
                running_selected <= 32'd0; running_fir <= 32'd0;
                running_peak0 <= 16'd0; running_peak1 <= 16'd0;
                running_clip0 <= 32'd0; running_clip1 <= 32'd0;
            end else begin
                window_cycle <= window_cycle + 1'b1;
                running_count0 <= next_count0; running_count1 <= next_count1;
                running_selected <= next_selected; running_fir <= next_fir;
                running_peak0 <= next_peak0; running_peak1 <= next_peak1;
                running_clip0 <= next_clip0; running_clip1 <= next_clip1;
            end
        end
    end
endmodule

`default_nettype wire
