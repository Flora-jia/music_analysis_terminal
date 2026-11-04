`timescale 1ns / 1ps
`default_nettype none

// Frequency-domain analysis chain:
//   xfft_0 -> cordic_translate_0 -> fft_peak_search
//
// External logic only needs to provide one complete FFT AXI-Stream frame.
// The FFT configuration channel is handled internally after reset.
//
// Ǩ��˵��(16384 -> 4096):
//   1. FFT_CONFIG_TDATA 16'h5555 -> 16'h1FFF(12��ȫ����, forward)
//   2. bin ����λ�� 14 -> 12(BIN_WIDTH)
//   3. FUND_MIN_BIN/FUND_MAX_BIN �ĵ���Ƶ��Χ(13~512)
//   4. CORDIC tuser ��Ϊ 14 bit(IP δ������), ��λ�� 0, �� 12 bit ���� bin ��
//   5. ���� fundamental_mag_left/right ͸���� peak_result_pack �������߲�ֵ
module fft_spectrum_chain #(
    parameter [15:0] FFT_CONFIG_TDATA      = 16'h1557, // 4096�? forward, 12级全缩放
    parameter integer BIN_WIDTH            = 12,       // log2(4096)
    parameter integer FUND_MIN_BIN         = 13,       // ~50 Hz
    parameter integer FUND_MAX_BIN         = 512,      // ~2 kHz
    parameter integer PEAK_THRESHOLD       = 100,
    parameter integer PEAK_SEPARATION_BINS = 5,
    parameter integer FFT_TUSER_WIDTH      = 24,       // FFT v9.1 m_axis_data_tuser 固定 24bit, �? log2(N) 才是 bin �?
    parameter integer CORDIC_TUSER_WIDTH   = 14        // 现有 cordic_translate_0 �? tuser 位宽
) (
    input  wire        clk,
    input  wire        rst_n,

    // Assert together with the start of the corresponding FFT input frame.
    input  wire        start_measure_pulse,

    // FFT input AXI-Stream.
    input  wire [31:0] s_axis_fft_tdata,
    input  wire        s_axis_fft_tvalid,
    output wire        s_axis_fft_tready,
    input  wire        s_axis_fft_tlast,

    // Shared CORDIC bus: observers use valid && ready, never stall independently.
    output wire [15:0] spectrum_magnitude,
    output wire [11:0] spectrum_bin,
    output wire spectrum_valid, spectrum_ready, spectrum_last,

    // Peak-search results. Bins are FFT output bin indexes.
    output wire [BIN_WIDTH-1:0] fundamental_bin,
    output wire [15:0]  fundamental_magnitude,
    output wire [15:0]  fundamental_mag_left,
    output wire [15:0]  fundamental_mag_right,
    output wire [BIN_WIDTH-1:0] harmonic1_bin,
    output wire [15:0]  harmonic1_magnitude,
    output wire [BIN_WIDTH-1:0] harmonic2_bin,
    output wire [15:0]  harmonic2_magnitude,
    output wire         result_valid,

    output wire         spectrum_busy,
    output reg          fft_config_done,

    // FFT status and error observation.
    output wire [7:0]   fft_status_data,
    output wire         fft_status_valid,
    output wire         fft_overflow,
    output wire         fft_tlast_error,
    output wire         fft_channel_halt
);

    reg fft_config_tvalid;

    wire fft_config_tready;
    wire fft_config_fire;

    wire        fft_s_axis_data_tready;

    wire [31:0] fft_m_axis_data_tdata;
    wire [FFT_TUSER_WIDTH-1:0] fft_m_axis_data_tuser; // 24bit 端口, �? BIN_WIDTH 才是 XK_INDEX
    wire        fft_m_axis_data_tvalid;
    wire        fft_m_axis_data_tready;
    wire        fft_m_axis_data_tlast;

    wire [7:0]  fft_m_axis_status_tdata;
    wire        fft_m_axis_status_tvalid;
    wire        fft_m_axis_status_tready;

    wire event_frame_started;
    wire event_tlast_unexpected;
    wire event_tlast_missing;
    wire event_fft_overflow;
    wire event_status_channel_halt;
    wire event_data_in_channel_halt;
    wire event_data_out_channel_halt;

    wire [31:0] cordic_s_axis_cartesian_tdata;
    wire [CORDIC_TUSER_WIDTH-1:0] cordic_s_axis_cartesian_tuser;
    wire        cordic_s_axis_cartesian_tvalid;
    wire        cordic_s_axis_cartesian_tready;
    wire        cordic_s_axis_cartesian_tlast;

    wire [31:0] cordic_m_axis_dout_tdata;
    wire [CORDIC_TUSER_WIDTH-1:0] cordic_m_axis_dout_tuser;
    wire        cordic_m_axis_dout_tvalid;
    wire        cordic_m_axis_dout_tready;
    wire        cordic_m_axis_dout_tlast;

    wire        peak_s_axis_tready;
    wire        peak_measurement_busy;

    assign fft_config_fire = fft_config_tvalid && fft_config_tready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fft_config_tvalid <= 1'b0;
            fft_config_done   <= 1'b0;
        end else begin
            if (!fft_config_done) begin
                fft_config_tvalid <= 1'b1;

                if (fft_config_fire) begin
                    fft_config_tvalid <= 1'b0;
                    fft_config_done   <= 1'b1;
                end
            end else begin
                fft_config_tvalid <= 1'b0;
            end
        end
    end

    assign s_axis_fft_tready = fft_config_done && fft_s_axis_data_tready;

    xfft_0 u_xfft_0 (
        .aclk                         (clk),
        .aresetn                      (rst_n),
        .s_axis_config_tdata          (FFT_CONFIG_TDATA),
        .s_axis_config_tvalid         (fft_config_tvalid),
        .s_axis_config_tready         (fft_config_tready),
        .s_axis_data_tdata            (s_axis_fft_tdata),
        .s_axis_data_tvalid           (s_axis_fft_tvalid && fft_config_done),
        .s_axis_data_tready           (fft_s_axis_data_tready),
        .s_axis_data_tlast            (s_axis_fft_tlast),
        .m_axis_data_tdata            (fft_m_axis_data_tdata),
        .m_axis_data_tuser            (fft_m_axis_data_tuser),
        .m_axis_data_tvalid           (fft_m_axis_data_tvalid),
        .m_axis_data_tready           (fft_m_axis_data_tready),
        .m_axis_data_tlast            (fft_m_axis_data_tlast),
        .m_axis_status_tdata          (fft_m_axis_status_tdata),
        .m_axis_status_tvalid         (fft_m_axis_status_tvalid),
        .m_axis_status_tready         (fft_m_axis_status_tready),
        .event_frame_started          (event_frame_started),
        .event_tlast_unexpected       (event_tlast_unexpected),
        .event_tlast_missing          (event_tlast_missing),
        .event_fft_overflow           (event_fft_overflow),
        .event_status_channel_halt    (event_status_channel_halt),
        .event_data_in_channel_halt   (event_data_in_channel_halt),
        .event_data_out_channel_halt  (event_data_out_channel_halt)
    );

    assign cordic_s_axis_cartesian_tdata  = fft_m_axis_data_tdata;
    // CORDIC tuser 端口仍是 14 bit(未重生成), �? 2 bit �? 0, �? 12 bit �? bin 号�??
    assign cordic_s_axis_cartesian_tuser  =
        {{(CORDIC_TUSER_WIDTH-BIN_WIDTH){1'b0}}, fft_m_axis_data_tuser[BIN_WIDTH-1:0]};
    assign cordic_s_axis_cartesian_tvalid = fft_m_axis_data_tvalid;
    assign cordic_s_axis_cartesian_tlast  = fft_m_axis_data_tlast;
    assign fft_m_axis_data_tready         = cordic_s_axis_cartesian_tready;

    cordic_translate_0 u_cordic_translate (
        .aclk                       (clk),
        .aresetn                    (rst_n),
        .s_axis_cartesian_tvalid    (cordic_s_axis_cartesian_tvalid),
        .s_axis_cartesian_tready    (cordic_s_axis_cartesian_tready),
        .s_axis_cartesian_tuser     (cordic_s_axis_cartesian_tuser),
        .s_axis_cartesian_tlast     (cordic_s_axis_cartesian_tlast),
        .s_axis_cartesian_tdata     (cordic_s_axis_cartesian_tdata),
        .m_axis_dout_tvalid         (cordic_m_axis_dout_tvalid),
        .m_axis_dout_tready         (cordic_m_axis_dout_tready),
        .m_axis_dout_tuser          (cordic_m_axis_dout_tuser),
        .m_axis_dout_tlast          (cordic_m_axis_dout_tlast),
        .m_axis_dout_tdata          (cordic_m_axis_dout_tdata)
    );

    assign cordic_m_axis_dout_tready = peak_s_axis_tready;
    assign spectrum_magnitude = cordic_m_axis_dout_tdata[15:0];
    assign spectrum_bin = cordic_m_axis_dout_tuser[11:0];
    assign spectrum_valid = cordic_m_axis_dout_tvalid;
    assign spectrum_ready = peak_s_axis_tready;
    assign spectrum_last = cordic_m_axis_dout_tlast;


    fft_peak_search #(
        .BIN_WIDTH            (BIN_WIDTH),
        .FUND_MIN_BIN         (FUND_MIN_BIN),
        .FUND_MAX_BIN         (FUND_MAX_BIN),
        .PEAK_THRESHOLD       (PEAK_THRESHOLD),
        .PEAK_SEPARATION_BINS (PEAK_SEPARATION_BINS)
    ) u_fft_peak_search (
        .clk                    (clk),
        .rst_n                  (rst_n),
        .start_measure_pulse    (start_measure_pulse),
        .measurement_busy       (peak_measurement_busy),
        .s_axis_magnitude       (cordic_m_axis_dout_tdata[15:0]),
        .s_axis_bin_index       (cordic_m_axis_dout_tuser[BIN_WIDTH-1:0]),
        .s_axis_tvalid          (cordic_m_axis_dout_tvalid),
        .s_axis_tready          (peak_s_axis_tready),
        .s_axis_tlast           (cordic_m_axis_dout_tlast),
        .fundamental_bin        (fundamental_bin),
        .fundamental_magnitude  (fundamental_magnitude),
        .fundamental_mag_left   (fundamental_mag_left),
        .fundamental_mag_right  (fundamental_mag_right),
        .harmonic1_bin          (harmonic1_bin),
        .harmonic1_magnitude    (harmonic1_magnitude),
        .harmonic2_bin          (harmonic2_bin),
        .harmonic2_magnitude    (harmonic2_magnitude),
        .result_valid           (result_valid)
    );

    assign fft_m_axis_status_tready = 1'b1;
    assign fft_status_data          = fft_m_axis_status_tdata;
    assign fft_status_valid         = fft_m_axis_status_tvalid;

    assign spectrum_busy    = peak_measurement_busy;
    assign fft_overflow     = event_fft_overflow;
    assign fft_tlast_error  = event_tlast_unexpected || event_tlast_missing;
    assign fft_channel_halt =
        event_status_channel_halt ||
        event_data_in_channel_halt ||
        event_data_out_channel_halt;

endmodule

`default_nettype wire
