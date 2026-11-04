`timescale 1ns / 1ps
`default_nettype none

// FFT acceleration wrapper for integration into teammate A's project.
//
// Wraps frame_auto_trigger + audio_fft_top into ONE module with a minimal
// interface, so teammate A only instantiates this single block:
//
//   FIR output (sample_data/sample_valid) --> fft_accel_wrapper --> m_axis_* --> axi_dma
//
// Clock: connect `clk` to teammate A's FCLK_CLK0 (50 MHz). The FFT chain is
// clock-frequency independent (data rate is only 16 kHz), so 50 MHz works
// with the same timing as the previously verified 100 MHz build.
//
// The auto-trigger starts frames automatically; no PS control is needed.

module fft_accel_wrapper (
    input  wire clk,      // 50 MHz (teammate A's FCLK_CLK0)
    input  wire rst_n,    // active-low reset (peripheral_aresetn)

    // ---- FIR input (16-bit signed sample stream) ----
    input  wire signed [15:0] sample_data,
    input  wire               sample_valid,
    output wire               sample_ready,

    // ---- AXI-Stream output -> axi_dma S2MM ----
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast,

    // ---- 错误观测（步骤1：从 audio_fft_top 透传）----
    output wire [15:0] err_ovfl_cnt,
    output wire [15:0] err_tlast_cnt,
    output wire [15:0] err_frame_cnt,
    output wire        fft_config_done,
    output wire        frame_error,
    output wire        fft_overflow,
    output wire        fft_tlast_error,
    output wire [7:0]  fft_status_data,
    output wire        fft_status_valid,

    // ---- Debug / ILA taps ----
    output wire [11:0] fundamental_bin,
    output wire [15:0] fundamental_magnitude,
    output wire        result_valid
);

    wire start_pulse, replay_valid, replay_ready, replay_last;
    wire signed [15:0] replay_data;
    wire [31:0] overlap_frame, scheduled, launched, scheduler_drop, copy_error;
    wire [31:0] source_drop, pack_drop, task_cycles, max_task_cycles;
    wire [63:0] overlap_first, source_count;
    wire [12:0] copy_count, replay_count;
    wire [3:0] overlap_state;
    wire frame_busy_w, spectrum_busy_w;
    assign sample_ready=rst_n;
    pcm_overlap_buffer u_overlap (
        .clk(clk), .rst_n(rst_n), .pcm_data(sample_data), .pcm_valid(sample_valid),
        .launch_ready(fft_config_done && !frame_busy_w && !spectrum_busy_w),
        .analysis_done(result_valid), .frame_start(start_pulse),
        .frame_id(overlap_frame), .first_seq(overlap_first),
        .replay_data(replay_data), .replay_valid(replay_valid),
        .replay_ready(replay_ready), .replay_last(replay_last),
        .source_count(source_count), .source_write_drop_count(source_drop),
        .scheduled_count(scheduled), .launched_count(launched),
        .scheduler_drop_count(scheduler_drop), .snapshot_copy_error_count(copy_error),
        .last_copy_count(copy_count), .last_replay_count(replay_count),
        .task_cycles(task_cycles), .max_task_cycles(max_task_cycles), .debug_state(overlap_state)
    );
`ifndef PL2_NO_ILA
    ila_pl2 u_ila_pl2 (
        .clk(clk), .probe0(source_count), .probe1(overlap_first), .probe2(overlap_frame),
        .probe3(scheduled), .probe4(launched), .probe5(scheduler_drop),
        .probe6(copy_error), .probe7(pack_drop), .probe8({6'd0,copy_count,replay_count}),
        .probe9(task_cycles), .probe10(max_task_cycles),
        .probe11({overlap_state, sample_valid, start_pulse, replay_valid && replay_ready, result_valid})
    );
`endif

    audio_fft_top u_fft (
        .clk          (clk),
        .rst_n        (rst_n),
        .sample_data  (replay_data),
        .sample_valid (replay_valid),
        .sample_ready (replay_ready),
        .start_pulse  (start_pulse),
        .scheduled_frame(overlap_frame), .window_first(overlap_first),
        .source_drop(source_drop), .prepack_drop(scheduler_drop+copy_error),
        .pack_drop_count(pack_drop),
        // status outputs
        .frame_busy         (frame_busy_w),
        .frame_done         (),
        .frame_error        (frame_error),
        .spectrum_busy      (spectrum_busy_w),
        .result_valid       (result_valid),
        .fft_status_data    (fft_status_data),
        .fft_status_valid   (fft_status_valid),
        .fft_overflow       (fft_overflow),
        .fft_tlast_error    (fft_tlast_error),
        .fft_config_done    (fft_config_done),
        .err_ovfl_cnt       (err_ovfl_cnt),
        .err_tlast_cnt      (err_tlast_cnt),
        .err_frame_cnt      (err_frame_cnt),
        .fundamental_bin       (fundamental_bin),
        .fundamental_magnitude (fundamental_magnitude),
        .fundamental_mag_left  (),
        .fundamental_mag_right (),
        .m_axis_tdata  (m_axis_tdata),
        .m_axis_tvalid (m_axis_tvalid),
        .m_axis_tready (m_axis_tready),
        .m_axis_tlast  (m_axis_tlast)
    );

endmodule

`default_nettype wire

