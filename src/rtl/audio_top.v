// MERGED: SPEC v2 DMA0 + model 0xA55A0402 DMA1 + existing LCD/touch/Line Out.
`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// audio_top : top-level RTL
//   Wraps Block Design (Audio_wrapper) + FIR + FFT chain
//
// PCM observation path:
//   ES8388 -> i2s_receiver_0 -> TID0 selector -> FIR -> scale/debug taps
// FFT/DMA input: scaled real PCM by default; FFT_USE_DDS=1 selects archived DDS reference.
//
// Clock domains:
//   - FCLK_CLK0 (50 MHz, from PS): main processing clock (m_axis_aud/fir/fft/dma)
//   - sys_clk (50 MHz crystal): only feeds clk_wiz to make aud_mclk (12.288 MHz)
//
// The FIR output is non-blocking; FFT sample_ready is an observation tap.
// PL FFT diagnostics retain their frame-gap counters. The PCM DMA tap is independent.
//////////////////////////////////////////////////////////////////////////////////

module audio_top #(
    // Live PCM experiment. Verified DDS artifacts are archived separately.
    // Both data and valid are selected by this parameter.
    parameter integer FFT_USE_DDS = 0,
    // Backlight diagnostic: 1 = always on; 0 = follow Video Out locked.
    parameter integer LCD_FORCE_BACKLIGHT = 1,
    // 1: known-good PL timing/colorbars; 0: normal PS framebuffer path.
    parameter integer LCD_PL_SELFTEST = 0
) (
    // DDR
    inout  [14:0] DDR_addr,
    inout  [2:0]  DDR_ba,
    inout         DDR_cas_n,
    inout         DDR_ck_n,
    inout         DDR_ck_p,
    inout         DDR_cke,
    inout         DDR_cs_n,
    inout  [3:0]  DDR_dm,
    inout  [31:0] DDR_dq,
    inout  [3:0]  DDR_dqs_n,
    inout  [3:0]  DDR_dqs_p,
    inout         DDR_odt,
    inout         DDR_ras_n,
    inout         DDR_reset_n,
    inout         DDR_we_n,
    // FIXED_IO
    inout         FIXED_IO_ddr_vrn,
    inout         FIXED_IO_ddr_vrp,
    inout  [53:0] FIXED_IO_mio,
    inout         FIXED_IO_ps_clk,
    inout         FIXED_IO_ps_porb,
    inout         FIXED_IO_ps_srstb,
    // Audio
    input         aud_adc_data,
    output        aud_dac_data,
    inout         aud_iic_scl_io,
    inout         aud_iic_sda_io,
    output        aud_lrclk,
    output        aud_mclk,
    output        aud_sclk,
    // System clock (50 MHz crystal -> clk_wiz -> aud_mclk)
    input         sys_clk,
    // LCD output: native 24-bit video is truncated to the RGB565 panel bus.
    output [15:0] lcd_rgb,
    output        lcd_de,
    output        lcd_hs,
    output        lcd_vs,
    output        lcd_pclk,
    output        lcd_bl,
    output        touch_reset_n
);

    // ---- processing clock & reset (exported from BD) ----
    wire         fclk_clk0;
    wire         peripheral_aresetn;
    // ---- clk_wiz lock status (exported from BD) ----
    wire         locked;
    // These copies are for the 50 MHz ILA only. Codec/RX functional nets stay direct.
    wire dbg_aud_sclk;
    wire dbg_aud_lrclk;
    wire dbg_aud_adc_data;
    wire dbg_locked;
    // IIC observation order: scl_i, scl_o, scl_t, sda_i, sda_o, sda_t.
    // *_t=1 releases the IOBUF; *_i reads its physical pad feedback.
    wire [5:0] iic_debug_async;
    wire [5:0] dbg_iic_lines;
    wire dbg_iic_tick;
    reg [4:0] iic_debug_divider;
    // ---- I2S Receiver AXI-Stream (exported from BD) ----
    wire [31:0]  m_axis_aud_tdata;
    wire [2:0] m_axis_aud_tid;
    wire m_axis_aud_tready;
    wire         m_axis_aud_tvalid;

    // ---- Channel selection and raw PCM capture diagnostics ----
    wire [31:0] mono_tdata;
    wire mono_tvalid;
    wire mono_tready;
    wire signed [15:0] raw_pcm;
    wire rx_fire;
    wire selected_pcm_fire;
    wire [31:0] rx_count0, rx_count1;
    wire [31:0] selected_pcm_count, fir_valid_count;
    wire [15:0] rx_peak0, rx_peak1;
    wire [31:0] rx_clip_count0, rx_clip_count1;
    wire [31:0] capture_window_id;
    wire capture_snapshot_valid;

    // ---- FIR output ----
    wire [23:0]  fir_tdata;
    wire         fir_tvalid;

    // ---- FIR -> FFT (16-bit signed) ----
    wire signed [15:0] sample_data;
    wire         sample_valid;

    // ---- FFT -> DMA ----
    wire [31:0]  stream_tdata;
    wire [3:0]   stream_tkeep;
    wire         stream_tvalid;
    wire         stream_tready;
    wire         stream_tlast;

    // ---- Step 1 error observation (mark_debug for ILA) ----
    wire [15:0]  err_ovfl_cnt;
    wire [15:0]  err_tlast_cnt;
    wire [15:0]  err_frame_cnt;
    wire         fft_config_done;

    // ---- debug taps (mark_debug for ILA) ----
    wire [11:0]  fundamental_bin;
    wire [15:0]  fundamental_magnitude;
    wire         result_valid;

    // Read-only frame and AXI handshake observations.

    // ---- LCD video from the BD, independent of the audio datapath ----
    wire [23:0] lcd_video_data;
    wire        lcd_video_active;
    wire        lcd_video_hsync;
    wire        lcd_video_vsync;
    wire        lcd_video_locked;
    wire        lcd_pixel_clk;


    // Independent DMA1: training-aligned model spectrum from PRE-FIR ADC.
    wire [31:0] model_tdata;
    wire model_tvalid, model_tready, model_tlast, model_dma_resetn;
    wire model_resetn = peripheral_aresetn && model_dma_resetn;
    music_fft1024_batch u_model (
        .clk(fclk_clk0), .rst_n(model_resetn),
        .pcm(raw_pcm), .pcm_valid(selected_pcm_fire),
        .m_tdata(model_tdata), .m_tvalid(model_tvalid),
        .m_tready(model_tready), .m_tlast(model_tlast)
    );

    // ================= Block Design =================
    Audio_iic_debug_wrapper u_audio (
        .DDR_addr(DDR_addr),
        .DDR_ba(DDR_ba),
        .DDR_cas_n(DDR_cas_n),
        .DDR_ck_n(DDR_ck_n),
        .DDR_ck_p(DDR_ck_p),
        .DDR_cke(DDR_cke),
        .DDR_cs_n(DDR_cs_n),
        .DDR_dm(DDR_dm),
        .DDR_dq(DDR_dq),
        .DDR_dqs_n(DDR_dqs_n),
        .DDR_dqs_p(DDR_dqs_p),
        .DDR_odt(DDR_odt),
        .DDR_ras_n(DDR_ras_n),
        .DDR_reset_n(DDR_reset_n),
        .DDR_we_n(DDR_we_n),
        .FCLK_CLK0(fclk_clk0),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),
        .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio),
        .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb),
        .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
        .model_dma_resetn(model_dma_resetn),
        .S_AXIS_S2MM_1_tdata(model_tdata), .S_AXIS_S2MM_1_tkeep(4'hF),
        .S_AXIS_S2MM_1_tvalid(model_tvalid), .S_AXIS_S2MM_1_tready(model_tready),
        .S_AXIS_S2MM_1_tlast(model_tlast),
        .S_AXIS_S2MM_tdata(stream_tdata),
        .S_AXIS_S2MM_tkeep(stream_tkeep),
        .S_AXIS_S2MM_tlast(stream_tlast),
        .S_AXIS_S2MM_tready(stream_tready),
        .S_AXIS_S2MM_tvalid(stream_tvalid),
        .aud_adc_data(aud_adc_data),
        .aud_dac_data(aud_dac_data),
        .aud_iic_scl_io(aud_iic_scl_io),
        .aud_iic_sda_io(aud_iic_sda_io),
        .dbg_iic_scl_i(iic_debug_async[0]), .dbg_iic_scl_o(iic_debug_async[1]),
        .dbg_iic_scl_t(iic_debug_async[2]), .dbg_iic_sda_i(iic_debug_async[3]),
        .dbg_iic_sda_o(iic_debug_async[4]), .dbg_iic_sda_t(iic_debug_async[5]),
        .aud_lrclk(aud_lrclk),
        .aud_mclk(aud_mclk),
        .aud_sclk(aud_sclk),
        .locked(locked),
        .m_axis_aud_tdata(m_axis_aud_tdata),
        .m_axis_aud_tid(m_axis_aud_tid),
        .m_axis_aud_tready(m_axis_aud_tready),
        .m_axis_aud_tvalid(m_axis_aud_tvalid),
        // TX is inactive: RX is the sole I2S clock master in step 3.
        .s_axis_aud_tdata(32'd0),
        .s_axis_aud_tid(3'd0),
        .s_axis_aud_tready(),
        .s_axis_aud_tvalid(1'b0),
        .peripheral_aresetn(peripheral_aresetn),
        .sys_clk(sys_clk),
        .lcd_bl(lcd_video_locked),
        .touch_reset_n(touch_reset_n),
        .lcd_pclk(lcd_pixel_clk),
        .lcd_video_active_video(lcd_video_active),
        .lcd_video_data(lcd_video_data),
        .lcd_video_field(),
        .lcd_video_hblank(),
        .lcd_video_hsync(lcd_video_hsync),
        .lcd_video_vblank(),
        .lcd_video_vsync(lcd_video_vsync)
    );

    // Keep one raw 33 MHz clock; forward it through the same ODDR structure
    // used by the verified 2026_full_2_v3 LCD implementation.
    ODDR #(
        .DDR_CLK_EDGE("OPPOSITE_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")
    ) u_lcd_pclk_oddr (
        .Q(lcd_pclk), .C(lcd_pixel_clk), .CE(1'b1),
        .D1(1'b1), .D2(1'b0), .R(1'b0), .S(1'b0)
    );

    generate
        if (LCD_PL_SELFTEST != 0) begin : g_lcd_pl_selftest
            audio_lcd_pl_selftest_800x480 u_lcd_test (
                .clk_lcd(lcd_pixel_clk),
                .lcd_rgb(lcd_rgb), .lcd_de(lcd_de),
                .lcd_hsync(lcd_hs), .lcd_vsync(lcd_vs)
            );
        end else begin : g_lcd_framebuffer
            // Framebuffer bytes are B/G/R; native Video Out syncs are high-active.
            assign lcd_rgb = lcd_video_active ?
                             {lcd_video_data[23:19], lcd_video_data[15:10], lcd_video_data[7:3]} : 16'b0;
            assign lcd_de = lcd_video_active;
            assign lcd_hs = ~lcd_video_hsync;
            assign lcd_vs = ~lcd_video_vsync;
        end
    endgenerate
    assign lcd_bl = (LCD_PL_SELFTEST != 0 || LCD_FORCE_BACKLIGHT != 0) ? 1'b1 : lcd_video_locked;

    // 32-bit words are fully valid (peak_result_pack emits full 32-bit words)
    assign stream_tkeep = 4'b1111;

    // Observe each independent IIC level through its own two-flop synchronizer.
    // These debug copies never drive the bus or the PS controller.
    genvar iic_bit;
    generate
        for (iic_bit = 0; iic_bit < 6; iic_bit = iic_bit + 1) begin : g_iic_debug
            xpm_cdc_single #(
                .DEST_SYNC_FF(2), .INIT_SYNC_FF(1),
                .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)
            ) u_cdc (
                .src_clk(1'b0), .src_in(iic_debug_async[iic_bit]),
                .dest_clk(fclk_clk0), .dest_out(dbg_iic_lines[iic_bit])
            );
        end
    endgenerate

    // Optional ILA storage qualification: one stored sample per 25 FCLK cycles.
    // 50 MHz / 25 = 2 MHz; depth 8192 covers 4.096 ms of an IIC transaction.
    always @(posedge fclk_clk0) begin
        if (!peripheral_aresetn || (iic_debug_divider == 5'd24))
            iic_debug_divider <= 5'd0;
        else
            iic_debug_divider <= iic_debug_divider + 1'b1;
    end
    assign dbg_iic_tick = (iic_debug_divider == 5'd24);

    // ================= Synchronize asynchronous observation signals =================
    // Two FCLK flops per independent single-bit signal; 20-40 ns sampling latency.
    // XPM constrains only the asynchronous path into its first synchronizer flop.
    // src_clk is unused with SRC_INPUT_REG=0; no source-domain register is added.
    // These are level observations, not a replacement for I2S sampling/decoding.
    xpm_cdc_single #(
        .DEST_SYNC_FF(2), .INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)
    ) u_dbg_cdc_sclk (
        .src_clk(1'b0), .src_in(aud_sclk),
        .dest_clk(fclk_clk0), .dest_out(dbg_aud_sclk)
    );

    xpm_cdc_single #(
        .DEST_SYNC_FF(2), .INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)
    ) u_dbg_cdc_lrclk (
        .src_clk(1'b0), .src_in(aud_lrclk),
        .dest_clk(fclk_clk0), .dest_out(dbg_aud_lrclk)
    );

    xpm_cdc_single #(
        .DEST_SYNC_FF(2), .INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)
    ) u_dbg_cdc_adc (
        .src_clk(1'b0), .src_in(aud_adc_data),
        .dest_clk(fclk_clk0), .dest_out(dbg_aud_adc_data)
    );

    xpm_cdc_single #(
        .DEST_SYNC_FF(2), .INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)
    ) u_dbg_cdc_locked (
        .src_clk(1'b0), .src_in(locked),
        .dest_clk(fclk_clk0), .dest_out(dbg_locked)
    );

    // ================= Select RX TID 0 before the single-channel FIR =================
    audio_mono_select #(.SELECT_TID(3'd0)) u_mono (
        .s_tdata(m_axis_aud_tdata), .s_tid(m_axis_aud_tid),
        .s_tvalid(m_axis_aud_tvalid), .s_tready(m_axis_aud_tready),
        .m_tdata(mono_tdata), .m_tvalid(mono_tvalid), .m_tready(mono_tready),
        .raw_pcm(raw_pcm), .rx_fire(rx_fire),
        .selected_pcm_fire(selected_pcm_fire)
    );

    audio_capture_debug #(.WINDOW_CYCLES(50000000)) u_capture_debug (
        .clk(fclk_clk0), .rst_n(peripheral_aresetn),
        .rx_tid(m_axis_aud_tid), .raw_pcm(raw_pcm),
        .rx_fire(rx_fire), .selected_pcm_fire(selected_pcm_fire),
        .fir_valid(fir_tvalid),
        .count0(rx_count0), .count1(rx_count1),
        .count_selected(selected_pcm_count), .count_fir(fir_valid_count),
        .peak0(rx_peak0), .peak1(rx_peak1),
        .clip_count0(rx_clip_count0), .clip_count1(rx_clip_count1),
        .window_id(capture_window_id), .snapshot_valid(capture_snapshot_valid)
    );

    // ================= FIR =================
    fir_audio u_fir (
        .clk(fclk_clk0),
        .s_tdata(mono_tdata),
        .s_tvalid(mono_tvalid),
        .s_tready(mono_tready),
        .m_tdata(fir_tdata),
        .m_tvalid(fir_tvalid)
    );

    // ================= 24-bit -> 16-bit scale =================
    fir_to_fft_scale u_scale (
        .s_tdata(fir_tdata),
        .s_tvalid(fir_tvalid),
        .m_tdata(sample_data),
        .m_tvalid(sample_valid)
    );

    // ================= Known FFT/DMA reference, independent of captured PCM =================
    wire signed [15:0] test_sample;
    wire test_valid;
    wire signed [15:0] fft_test_sample = test_sample >>> 2;
    wire signed [15:0] fft_sample_data;
    wire fft_sample_valid;
    wire fft_sample_ready;

    dds_tone_source #(
        .CLK_DIV(3125),       // 50 MHz / 3125 = 16 ksample/s
        .PHASE_WIDTH(16),
        .PHASE_INC(2048)      // 500 Hz, exact FFT bin 128 at N=4096
    ) u_dds (
        .clk(fclk_clk0), .rst_n(peripheral_aresetn),
        .sample_data(test_sample), .sample_valid(test_valid)
    );

    assign fft_sample_data = FFT_USE_DDS ? fft_test_sample : sample_data;
    assign fft_sample_valid = FFT_USE_DDS ? test_valid : sample_valid;

    // ================= FFT peak detection chain (teammate B) =================
    fft_accel_wrapper u_fft (
        .clk(fclk_clk0),
        .rst_n(peripheral_aresetn),
        .sample_data(fft_sample_data),
        .sample_valid(fft_sample_valid),
        .sample_ready(fft_sample_ready), // diagnostic only; no upstream buffering added
        .err_ovfl_cnt(err_ovfl_cnt),
        .err_tlast_cnt(err_tlast_cnt),
        .err_frame_cnt(err_frame_cnt),
        .fft_config_done(fft_config_done),
        .m_axis_tdata(stream_tdata),
        .m_axis_tvalid(stream_tvalid),
        .m_axis_tready(stream_tready),
        .m_axis_tlast(stream_tlast),
        .fundamental_bin(fundamental_bin),
        .fundamental_magnitude(fundamental_magnitude),
        .result_valid(result_valid)
    );

endmodule


// Standalone pixel generation; no VDMA, VTC, DDR or measurement-core dependency.
// The clock is still supplied by the existing BD LCD MMCM (PS FCLK0 -> 33 MHz).
module audio_lcd_pl_selftest_800x480 (
    input  wire        clk_lcd,
    output wire [15:0] lcd_rgb,
    output wire        lcd_de,
    output wire        lcd_hsync,
    output wire        lcd_vsync
);
    // FPGA configuration initialization; release timing reset on pixel-clock edges.
    reg [4:0] reset_pipe = 5'b00000;
    always @(posedge clk_lcd)
        reset_pipe <= {reset_pipe[3:0], 1'b1};

    wire [10:0] pixel_x;
    wire [9:0] pixel_y_unused;
    wire active_video;
    wire frame_start_unused;
    audio_lcd_ref_timing_800x480 u_timing (
        .clk_lcd(clk_lcd), .rst_n(reset_pipe[4]),
        .pixel_x(pixel_x), .pixel_y(pixel_y_unused),
        .active_video(active_video),
        .lcd_hsync(lcd_hsync), .lcd_vsync(lcd_vsync),
        .frame_start(frame_start_unused)
    );

    reg [15:0] bar_rgb;
    always @* begin
        if      (pixel_x < 11'd100) bar_rgb = 16'hFFFF;
        else if (pixel_x < 11'd200) bar_rgb = 16'hFFE0;
        else if (pixel_x < 11'd300) bar_rgb = 16'h07FF;
        else if (pixel_x < 11'd400) bar_rgb = 16'h07E0;
        else if (pixel_x < 11'd500) bar_rgb = 16'hF81F;
        else if (pixel_x < 11'd600) bar_rgb = 16'hF800;
        else if (pixel_x < 11'd700) bar_rgb = 16'h001F;
        else                       bar_rgb = 16'h0000;
    end
    assign lcd_de = active_video;
    assign lcd_rgb = active_video ? bar_rgb : 16'h0000;
endmodule

// Timing copied from the user-verified 2026_full_2_v3 reference; only module name changed.
`timescale 1ns / 1ps

module audio_lcd_ref_timing_800x480 (
    input  wire        clk_lcd,
    input  wire        rst_n,
    output reg  [10:0] pixel_x,
    output reg  [9:0]  pixel_y,
    output reg         active_video,
    output reg         lcd_hsync,
    output reg         lcd_vsync,
    output reg         frame_start
);

    localparam H_ACTIVE = 11'd800;
    localparam H_SYNC   = 11'd128;
    localparam H_BACK   = 11'd88;
    localparam H_FRONT  = 11'd40;
    localparam H_TOTAL  = 11'd1056;

    localparam V_ACTIVE = 10'd480;
    localparam V_SYNC   = 10'd2;
    localparam V_BACK   = 10'd33;  // 25 back porch + 8 top border
    localparam V_FRONT  = 10'd10;  // 2 front porch + 8 bottom border
    localparam V_TOTAL  = 10'd525;

    localparam H_START  = H_SYNC + H_BACK;
    localparam H_END    = H_START + H_ACTIVE;
    localparam V_START  = V_SYNC + V_BACK;
    localparam V_END    = V_START + V_ACTIVE;

    reg [10:0] h_cnt;
    reg [9:0]  v_cnt;

    always @(posedge clk_lcd) begin
        if (!rst_n) begin
            h_cnt <= 11'd0;
            v_cnt <= 10'd0;
        end else if (h_cnt == H_TOTAL - 1'b1) begin
            h_cnt <= 11'd0;
            if (v_cnt == V_TOTAL - 1'b1)
                v_cnt <= 10'd0;
            else
                v_cnt <= v_cnt + 1'b1;
        end else begin
            h_cnt <= h_cnt + 1'b1;
        end
    end

    wire in_h_active = (h_cnt >= H_START) && (h_cnt < H_END);
    wire in_v_active = (v_cnt >= V_START) && (v_cnt < V_END);

    always @(posedge clk_lcd) begin
        if (!rst_n) begin
            pixel_x      <= 11'd0;
            pixel_y      <= 10'd0;
            active_video <= 1'b0;
            lcd_hsync    <= 1'b1;
            lcd_vsync    <= 1'b1;
            frame_start  <= 1'b0;
        end else begin
            active_video <= in_h_active && in_v_active;
            pixel_x      <= in_h_active ? (h_cnt - H_START) : 11'd0;
            pixel_y      <= in_v_active ? (v_cnt - V_START) : 10'd0;
            lcd_hsync    <= (h_cnt >= H_SYNC);
            lcd_vsync    <= (v_cnt >= V_SYNC);
            frame_start  <= (h_cnt == 11'd0) && (v_cnt == 10'd0);
        end
    end

endmodule
