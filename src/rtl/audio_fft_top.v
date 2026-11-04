`timescale 1ns / 1ps
`default_nettype none

// ����: FIR��� -> fft_frame_controller -> fft_spectrum_chain -> peak_result_pack -> AXI-Stream
//
// ����: 4096�� FFT, 16 kHz ����, Ƶ�ʷֱ���Լ 3.906 Hz, 440 Hz -> bin �� 113��
//
// ˵��: ��ģ��ֻ��� AXI-Stream(m_axis_*)�������� AXI DMA��PS AXI-Lite ���ơ�
//       DDR ������ Block Design �����(�����ײ���ָ��)��
module audio_fft_top #(
    parameter integer FRAME_LEN            = 4096,
    parameter integer INDEX_WIDTH          = 12,
    parameter integer BIN_WIDTH            = 12,
    parameter [15:0] FFT_CONFIG_TDATA      = 16'h1557,
    parameter integer FUND_MIN_BIN         = 13,
    parameter integer FUND_MAX_BIN         = 512,
    parameter integer PEAK_THRESHOLD       = 100,
    parameter integer PEAK_SEPARATION_BINS = 5
) (
    input  wire clk,
    input  wire rst_n,

    // ---- ������(���� FIR) ----
    input  wire signed [15:0] sample_data,
    input  wire               sample_valid,
    output wire               sample_ready,

    // ---- ����һ֡(���� AXI-Lite / GPIO / �Զ�������) ----
    input  wire start_pulse,
    input wire [31:0] scheduled_frame, source_drop, prepack_drop,
    input wire [63:0] window_first,
    output wire [31:0] pack_drop_count,

    // ---- ״̬�۲�(ILA) ----
    output wire        frame_busy,
    output wire        frame_done,
    output wire        frame_error,
    output wire [15:0] err_ovfl_cnt,
    output wire [15:0] err_tlast_cnt,
    output wire [15:0] err_frame_cnt,
    output wire        fft_config_done,
    output wire        spectrum_busy,
    output wire        result_valid,
    output wire [7:0]  fft_status_data,
    output wire        fft_status_valid,
    output wire        fft_overflow,
    output wire        fft_tlast_error,

    // ---- ��ֵ����(ILA ����) ----
    output wire [BIN_WIDTH-1:0] fundamental_bin,
    output wire [15:0]  fundamental_magnitude,
    output wire [15:0]  fundamental_mag_left,
    output wire [15:0]  fundamental_mag_right,

    // ---- ������ AXI-Stream -> AXI DMA S2MM ----
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);

    // frame_controller -> spectrum_chain
    wire [31:0] fft_s_axis_data_tdata;
    wire        fft_s_axis_data_tvalid;
    wire        fft_s_axis_data_tready;
    wire        fft_s_axis_data_tlast;

    wire [BIN_WIDTH-1:0] fundamental_bin_w;
    wire [15:0]  fundamental_magnitude_w;
    wire [15:0]  fundamental_mag_left_w;
    wire [15:0]  fundamental_mag_right_w;
    wire [BIN_WIDTH-1:0] harmonic1_bin_w;
    wire [15:0]  harmonic1_magnitude_w;
    wire [BIN_WIDTH-1:0] harmonic2_bin_w;
    wire [15:0]  harmonic2_magnitude_w;
    wire        result_valid_w;

    // ---- 步骤1：错误事件计数（累计，供 ILA 观测；持续增长=持续出错）----
    reg [15:0] err_ovfl_cnt_r, err_tlast_cnt_r, err_frame_cnt_r;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            err_ovfl_cnt_r  <= 16'd0;
            err_tlast_cnt_r <= 16'd0;
            err_frame_cnt_r <= 16'd0;
        end else begin
            if (fft_overflow)    err_ovfl_cnt_r  <= err_ovfl_cnt_r  + 1'b1;
            if (fft_tlast_error) err_tlast_cnt_r <= err_tlast_cnt_r + 1'b1;
            if (frame_error)     err_frame_cnt_r <= err_frame_cnt_r + 1'b1;
        end
    end
    assign err_ovfl_cnt  = err_ovfl_cnt_r;
    assign err_tlast_cnt = err_tlast_cnt_r;
    assign err_frame_cnt = err_frame_cnt_r;

    fft_frame_controller #(
        .FRAME_LEN   (FRAME_LEN),
        .INDEX_WIDTH (INDEX_WIDTH)
    ) u_frame_ctrl (
        .clk                    (clk),
        .rst_n                  (rst_n),
        .start_pulse            (start_pulse),
        .sample_data            (sample_data),
        .sample_valid           (sample_valid),
        .sample_ready           (sample_ready),
        .fft_s_axis_data_tdata  (fft_s_axis_data_tdata),
        .fft_s_axis_data_tvalid (fft_s_axis_data_tvalid),
        .fft_s_axis_data_tready (fft_s_axis_data_tready),
        .fft_s_axis_data_tlast  (fft_s_axis_data_tlast),
        .frame_busy             (frame_busy),
        .frame_done             (frame_done),
        .frame_error            (frame_error)
    );

    wire [31:0] window_data;
    wire window_valid, window_ready, window_last;
    axis_hann4096 u_hann (
        .clk(clk), .rst_n(rst_n),
        .s_tdata(fft_s_axis_data_tdata), .s_tvalid(fft_s_axis_data_tvalid),
        .s_tready(fft_s_axis_data_tready), .s_tlast(fft_s_axis_data_tlast),
        .m_tdata(window_data), .m_tvalid(window_valid),
        .m_tready(window_ready), .m_tlast(window_last)
    );

    wire [15:0] spectrum_magnitude;
    wire [11:0] spectrum_bin;
    wire spectrum_valid, spectrum_ready, spectrum_last;
    wire [31:0] spectrum_dropped_frames, spectrum_sent_frames;

    fft_spectrum_chain #(
        .FFT_CONFIG_TDATA      (FFT_CONFIG_TDATA),
        .BIN_WIDTH             (BIN_WIDTH),
        .FUND_MIN_BIN          (FUND_MIN_BIN),
        .FUND_MAX_BIN          (FUND_MAX_BIN),
        .PEAK_THRESHOLD        (PEAK_THRESHOLD),
        .PEAK_SEPARATION_BINS  (PEAK_SEPARATION_BINS)
    ) u_spectrum (
        .clk                   (clk),
        .rst_n                 (rst_n),
        .start_measure_pulse   (start_pulse),
        .spectrum_magnitude(spectrum_magnitude), .spectrum_bin(spectrum_bin),
        .spectrum_valid(spectrum_valid), .spectrum_ready(spectrum_ready),
        .spectrum_last(spectrum_last),

        .s_axis_fft_tdata      (window_data),
        .s_axis_fft_tvalid     (window_valid),
        .s_axis_fft_tready     (window_ready),
        .s_axis_fft_tlast      (window_last),
        .fundamental_bin       (fundamental_bin_w),
        .fundamental_magnitude (fundamental_magnitude_w),
        .fundamental_mag_left  (fundamental_mag_left_w),
        .fundamental_mag_right (fundamental_mag_right_w),
        .harmonic1_bin         (harmonic1_bin_w),
        .harmonic1_magnitude   (harmonic1_magnitude_w),
        .harmonic2_bin         (harmonic2_bin_w),
        .harmonic2_magnitude   (harmonic2_magnitude_w),
        .result_valid          (result_valid_w),
        .spectrum_busy         (spectrum_busy),
        .fft_config_done       (fft_config_done),
        .fft_status_data       (fft_status_data),
        .fft_status_valid      (fft_status_valid),
        .fft_overflow          (fft_overflow),
        .fft_tlast_error       (fft_tlast_error),
        .fft_channel_halt      ()
    );

    spectrum_frame_pack u_pack (
        .clk(clk), .rst_n(rst_n), .frame_start(start_pulse),
        .scheduled_frame(scheduled_frame), .window_first(window_first),
        .source_drop(source_drop), .prepack_drop(prepack_drop),
        .sample_accept(sample_valid && sample_ready),
        .fft_input_fire(window_valid && window_ready),
        .frame_error(frame_error), .fft_overflow(fft_overflow),
        .fft_tlast_error(fft_tlast_error),
        .s_magnitude(spectrum_magnitude), .s_bin(spectrum_bin),
        .s_valid(spectrum_valid), .s_ready(spectrum_ready), .s_last(spectrum_last),
        .result_valid(result_valid_w), .peak_bin(fundamental_bin_w),
        .peak_mag(fundamental_magnitude_w), .peak_left(fundamental_mag_left_w),
        .peak_right(fundamental_mag_right_w),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast),
        .dropped_frames(spectrum_dropped_frames), .sent_frames(spectrum_sent_frames)
    );

    assign pack_drop_count = spectrum_dropped_frames;
    assign result_valid          = result_valid_w;
    assign fundamental_bin       = fundamental_bin_w;
    assign fundamental_magnitude = fundamental_magnitude_w;
    assign fundamental_mag_left  = fundamental_mag_left_w;
    assign fundamental_mag_right = fundamental_mag_right_w;

endmodule

`default_nettype wire
