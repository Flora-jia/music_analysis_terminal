`timescale 1ns / 1ps
`default_nettype none

// Select the strongest local peak in the configured frequency interval.
// This is a dominant spectral peak, NOT a validated fundamental estimator.
// Strictly greater replacement gives the lower bin priority for equal peaks.
// Legacy harmonic outputs are reserved/zero: arbitrary peaks are not harmonics.
module fft_peak_search #(
    parameter integer BIN_WIDTH = 12,
    parameter integer FUND_MIN_BIN = 13,
    parameter integer FUND_MAX_BIN = 512,
    parameter integer PEAK_THRESHOLD = 100,
    parameter integer PEAK_SEPARATION_BINS = 5
) (
    input wire clk, rst_n,
    input wire start_measure_pulse,
    output wire measurement_busy,
    input wire [15:0] s_axis_magnitude,
    input wire [BIN_WIDTH-1:0] s_axis_bin_index,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    input wire s_axis_tlast,
    output reg [BIN_WIDTH-1:0] fundamental_bin,
    output reg [15:0] fundamental_magnitude,
    output reg [15:0] fundamental_mag_left,
    output reg [15:0] fundamental_mag_right,
    output wire [BIN_WIDTH-1:0] harmonic1_bin,
    output wire [15:0] harmonic1_magnitude,
    output wire [BIN_WIDTH-1:0] harmonic2_bin,
    output wire [15:0] harmonic2_magnitude,
    output reg result_valid
);
    reg active;
    reg [1:0] history_count;
    reg [BIN_WIDTH-1:0] previous_bin, previous_previous_bin;
    reg [15:0] previous_magnitude, previous_previous_magnitude;
    reg found;
    wire fire = s_axis_tvalid && s_axis_tready;
    wire is_peak = history_count == 2 &&
        previous_bin >= FUND_MIN_BIN && previous_bin <= FUND_MAX_BIN &&
        previous_previous_bin + 1'b1 == previous_bin &&
        previous_bin + 1'b1 == s_axis_bin_index &&
        previous_magnitude >= previous_previous_magnitude &&
        previous_magnitude > s_axis_magnitude &&
        previous_magnitude >= PEAK_THRESHOLD;
    assign measurement_busy = active;
    assign s_axis_tready = active;
    assign harmonic1_bin = 0;
    assign harmonic1_magnitude = 0;
    assign harmonic2_bin = 0;
    assign harmonic2_magnitude = 0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active <= 0; history_count <= 0; found <= 0;
            previous_bin <= 0; previous_previous_bin <= 0;
            previous_magnitude <= 0; previous_previous_magnitude <= 0;
            fundamental_bin <= 0; fundamental_magnitude <= 0;
            fundamental_mag_left <= 0; fundamental_mag_right <= 0;
            result_valid <= 0;
        end else begin
            result_valid <= 0;
            if (!active && start_measure_pulse) begin
                active <= 1; history_count <= 0; found <= 0;
                previous_bin <= 0; previous_previous_bin <= 0;
                previous_magnitude <= 0; previous_previous_magnitude <= 0;
                fundamental_bin <= 0; fundamental_magnitude <= 0;
                fundamental_mag_left <= 0; fundamental_mag_right <= 0;
            end else if (fire) begin
                if (is_peak && (!found || previous_magnitude > fundamental_magnitude)) begin
                    found <= 1;
                    fundamental_bin <= previous_bin;
                    fundamental_magnitude <= previous_magnitude;
                    fundamental_mag_left <= previous_previous_magnitude;
                    fundamental_mag_right <= s_axis_magnitude;
                end
                previous_previous_bin <= previous_bin;
                previous_previous_magnitude <= previous_magnitude;
                previous_bin <= s_axis_bin_index;
                previous_magnitude <= s_axis_magnitude;
                if (history_count != 2) history_count <= history_count + 1'b1;
                if (s_axis_tlast) begin
                    active <= 0;
                    result_valid <= 1;
                end
            end
        end
    end
endmodule
`default_nettype wire
