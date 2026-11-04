`timescale 1ns / 1ps
`default_nettype none

// Packs signed 16-bit real samples into 4096-point FFT input frames.
//
// Input samples come from fir_to_fft_scale in the 50 MHz PL clock domain.
// The FFT IP uses AXI-Stream input:
//   tdata[15:0]  = real part
//   tdata[31:16] = imaginary part, fixed to zero
//   tlast        = asserted on sample index 4095
//
// Ǩ��˵��: 16384 -> 4096 ֻ��������������, �߼���Ķ���
//   LAST_INDEX = FRAME_LEN-1 �Զ���Ϊ 4095, tlast �Զ����ڵ� 4095 ��������
module fft_frame_controller #(
    parameter integer FRAME_LEN   = 4096,
    parameter integer INDEX_WIDTH = 12
) (
    input  wire               clk,
    input  wire               rst_n,

    // One clk-cycle pulse. Starts one FFT frame when the controller is idle.
    input  wire               start_pulse,

    // Signed 16-bit sample stream after FIR scaling.
    input  wire signed [15:0] sample_data,
    input  wire               sample_valid,
    output wire               sample_ready,

    // AXI-Stream input side of the FFT IP.
    output wire [31:0]        fft_s_axis_data_tdata,
    output wire               fft_s_axis_data_tvalid,
    input  wire               fft_s_axis_data_tready,
    output wire               fft_s_axis_data_tlast,

    output wire               frame_busy,
    output reg                frame_done,

    // Sticky during one frame. Cleared by the next accepted start_pulse.
    // It means a valid sample arrived while the controller could not pass the
    // previous sample to FFT. In normal operation this should stay low.
    output reg                frame_error
);

    localparam [INDEX_WIDTH-1:0] LAST_INDEX = FRAME_LEN - 1;

    reg                      capturing;
    reg [INDEX_WIDTH-1:0]    sample_count;
    reg signed [15:0]        pending_data;
    reg                      pending_valid;
    reg                      pending_last;
    reg stalled;
    reg [15:0] stalled_data;

    wire                     fft_accept;
    wire                     load_sample;
    wire                     start_accepted;

    assign fft_accept    = pending_valid && fft_s_axis_data_tready;
    assign sample_ready  = capturing && (!pending_valid || fft_accept);
    assign load_sample   = sample_valid && sample_ready;
    assign start_accepted = start_pulse && !frame_busy;

    assign fft_s_axis_data_tdata  = {16'sd0, pending_data};
    assign fft_s_axis_data_tvalid = pending_valid;
    assign fft_s_axis_data_tlast  = pending_valid && pending_last;

    assign frame_busy = capturing || pending_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            capturing     <= 1'b0;
            sample_count  <= {INDEX_WIDTH{1'b0}};
            pending_data  <= 16'sd0;
            pending_valid <= 1'b0;
            pending_last  <= 1'b0;
            frame_done    <= 1'b0;
            frame_error   <= 1'b0;
            stalled <= 0; stalled_data <= 0;
        end else begin
            frame_done <= 1'b0;
            stalled <= sample_valid && !sample_ready;
            stalled_data <= sample_data;
            // A ready/valid source may hold valid during backpressure.
            // Only withdrawal/change of an outstanding sample is an error.
            if (stalled && (!sample_valid || sample_data != stalled_data)) frame_error <= 1'b1;

            if (start_accepted) begin
                capturing     <= 1'b1;
                sample_count  <= {INDEX_WIDTH{1'b0}};
                pending_data  <= 16'sd0;
                pending_valid <= 1'b0;
                pending_last  <= 1'b0;
                frame_error   <= 1'b0;
            stalled <= 0; stalled_data <= 0;
            end else begin
                if (fft_accept) begin
                    pending_valid <= 1'b0;

                    if (pending_last)
                        frame_done <= 1'b1;
                end

                if (load_sample) begin
                    pending_data  <= sample_data;
                    pending_valid <= 1'b1;
                    pending_last  <= (sample_count == LAST_INDEX);

                    if (sample_count == LAST_INDEX)
                        capturing <= 1'b0;
                    else
                        sample_count <= sample_count + 1'b1;
                end
            end
        end
    end

endmodule

`default_nettype wire
