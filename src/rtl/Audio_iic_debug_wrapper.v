// Hand-maintained diagnostic wrapper: identical IOBUF path plus six read-only taps.
// Original generated Audio_wrapper.v is unchanged.
//Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2020.2 (win64) Build 3064766 Wed Nov 18 09:12:45 MST 2020
//Date        : Thu Oct  8 22:45:21 2026
//Host        : LAPTOP-EBUKJ1O7 running 64-bit major release  (build 9200)
//Command     : generate_target Audio_wrapper.bd
//Design      : Audio_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module Audio_iic_debug_wrapper
   (DDR_addr,
    DDR_ba,
    DDR_cas_n,
    DDR_ck_n,
    DDR_ck_p,
    DDR_cke,
    DDR_cs_n,
    DDR_dm,
    DDR_dq,
    DDR_dqs_n,
    DDR_dqs_p,
    DDR_odt,
    DDR_ras_n,
    DDR_reset_n,
    DDR_we_n,
    FCLK_CLK0,
    FIXED_IO_ddr_vrn,
    FIXED_IO_ddr_vrp,
    FIXED_IO_mio,
    FIXED_IO_ps_clk,
    FIXED_IO_ps_porb,
    FIXED_IO_ps_srstb,
    model_dma_resetn,
    S_AXIS_S2MM_1_tdata, S_AXIS_S2MM_1_tkeep, S_AXIS_S2MM_1_tlast,
    S_AXIS_S2MM_1_tready, S_AXIS_S2MM_1_tvalid,
    S_AXIS_S2MM_tdata,
    S_AXIS_S2MM_tkeep,
    S_AXIS_S2MM_tlast,
    S_AXIS_S2MM_tready,
    S_AXIS_S2MM_tvalid,
    aud_adc_data,
    aud_dac_data,
    aud_iic_scl_io,
    aud_iic_sda_io,
    dbg_iic_scl_i,
    dbg_iic_scl_o,
    dbg_iic_scl_t,
    dbg_iic_sda_i,
    dbg_iic_sda_o,
    dbg_iic_sda_t,
    aud_lrclk,
    aud_mclk,
    aud_sclk,
    locked,
    m_axis_aud_tdata,
    m_axis_aud_tid,
    m_axis_aud_tready,
    m_axis_aud_tvalid,
    peripheral_aresetn,
    s_axis_aud_tdata,
    s_axis_aud_tid,
    s_axis_aud_tready,
    s_axis_aud_tvalid,
    sys_clk,
    lcd_bl,
    lcd_pclk,
    lcd_video_active_video,
    lcd_video_data,
    lcd_video_field,
    lcd_video_hblank,
    lcd_video_hsync,
    lcd_video_vblank,
    lcd_video_vsync,
    touch_reset_n);
  inout [14:0]DDR_addr;
  inout [2:0]DDR_ba;
  inout DDR_cas_n;
  inout DDR_ck_n;
  inout DDR_ck_p;
  inout DDR_cke;
  inout DDR_cs_n;
  inout [3:0]DDR_dm;
  inout [31:0]DDR_dq;
  inout [3:0]DDR_dqs_n;
  inout [3:0]DDR_dqs_p;
  inout DDR_odt;
  inout DDR_ras_n;
  inout DDR_reset_n;
  inout DDR_we_n;
  output FCLK_CLK0;
  inout FIXED_IO_ddr_vrn;
  inout FIXED_IO_ddr_vrp;
  inout [53:0]FIXED_IO_mio;
  inout FIXED_IO_ps_clk;
  inout FIXED_IO_ps_porb;
  inout FIXED_IO_ps_srstb;
  output model_dma_resetn;
  input [31:0] S_AXIS_S2MM_1_tdata;
  input [3:0] S_AXIS_S2MM_1_tkeep;
  input S_AXIS_S2MM_1_tlast, S_AXIS_S2MM_1_tvalid;
  output S_AXIS_S2MM_1_tready;
  input [31:0]S_AXIS_S2MM_tdata;
  input [3:0]S_AXIS_S2MM_tkeep;
  input S_AXIS_S2MM_tlast;
  output S_AXIS_S2MM_tready;
  input S_AXIS_S2MM_tvalid;
  input aud_adc_data;
  output aud_dac_data;
  inout aud_iic_scl_io;
  inout aud_iic_sda_io;
  output dbg_iic_scl_i;
  output dbg_iic_scl_o;
  output dbg_iic_scl_t;
  output dbg_iic_sda_i;
  output dbg_iic_sda_o;
  output dbg_iic_sda_t;
  output aud_lrclk;
  output aud_mclk;
  output aud_sclk;
  output locked;
  output [31:0]m_axis_aud_tdata;
  output [2:0]m_axis_aud_tid;
  input m_axis_aud_tready;
  output m_axis_aud_tvalid;
  output [0:0]peripheral_aresetn;
  input [31:0]s_axis_aud_tdata;
  input [2:0]s_axis_aud_tid;
  output s_axis_aud_tready;
  input s_axis_aud_tvalid;
  input sys_clk;

  // LCD pass-through from the current Audio BD.
  output wire lcd_bl;
  output wire lcd_pclk;
  output wire lcd_video_active_video;
  output wire [23:0]lcd_video_data;
  output wire lcd_video_field;
  output wire lcd_video_hblank;
  output wire lcd_video_hsync;
  output wire lcd_video_vblank;
  output wire lcd_video_vsync;
  output wire touch_reset_n;


  wire [14:0]DDR_addr;
  wire [2:0]DDR_ba;
  wire DDR_cas_n;
  wire DDR_ck_n;
  wire DDR_ck_p;
  wire DDR_cke;
  wire DDR_cs_n;
  wire [3:0]DDR_dm;
  wire [31:0]DDR_dq;
  wire [3:0]DDR_dqs_n;
  wire [3:0]DDR_dqs_p;
  wire DDR_odt;
  wire DDR_ras_n;
  wire DDR_reset_n;
  wire DDR_we_n;
  wire FCLK_CLK0;
  wire FIXED_IO_ddr_vrn;
  wire FIXED_IO_ddr_vrp;
  wire [53:0]FIXED_IO_mio;
  wire FIXED_IO_ps_clk;
  wire FIXED_IO_ps_porb;
  wire FIXED_IO_ps_srstb;
  wire [31:0]S_AXIS_S2MM_tdata;
  wire [3:0]S_AXIS_S2MM_tkeep;
  wire S_AXIS_S2MM_tlast;
  wire S_AXIS_S2MM_tready;
  wire S_AXIS_S2MM_tvalid;
  wire aud_adc_data;
  wire aud_dac_data;
  wire aud_iic_scl_i;
  wire aud_iic_scl_io;
  wire aud_iic_scl_o;
  wire aud_iic_scl_t;
  wire aud_iic_sda_i;
  wire aud_iic_sda_io;
  wire aud_iic_sda_o;
  wire aud_iic_sda_t;
  wire aud_lrclk;
  wire aud_mclk;
  wire aud_sclk;
  wire locked;
  wire [31:0]m_axis_aud_tdata;
  wire [2:0]m_axis_aud_tid;
  wire m_axis_aud_tready;
  wire m_axis_aud_tvalid;
  wire [0:0]peripheral_aresetn;
  wire [31:0]s_axis_aud_tdata;
  wire [2:0]s_axis_aud_tid;
  wire s_axis_aud_tready;
  wire s_axis_aud_tvalid;
  wire sys_clk;

  // PL IIC mode: bit0 selects override, bit1/2 release SCL/SDA.
  // I=0 in override mode; high is obtained exclusively by releasing T.
  wire [2:0] codec_iic_control;
  wire [9:0] codec_iic_feedback;
  wire scl_effective_o = codec_iic_control[0] ? 1'b0 : aud_iic_scl_o;
  wire sda_effective_o = codec_iic_control[0] ? 1'b0 : aud_iic_sda_o;
  wire scl_effective_t = codec_iic_control[0] ? codec_iic_control[1] : aud_iic_scl_t;
  wire sda_effective_t = codec_iic_control[0] ? codec_iic_control[2] : aud_iic_sda_t;
  assign codec_iic_feedback = {aud_iic_sda_t,aud_iic_sda_o,aud_iic_scl_t,aud_iic_scl_o,
                              sda_effective_t,sda_effective_o,aud_iic_sda_i,
                              scl_effective_t,scl_effective_o,aud_iic_scl_i};

  Audio Audio_i
       (.codec_iic_control(codec_iic_control),
        .codec_iic_feedback(codec_iic_feedback),
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
        .FCLK_CLK0(FCLK_CLK0),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),
        .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio),
        .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb),
        .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
        .model_dma_resetn(model_dma_resetn),
        .S_AXIS_S2MM_1_tdata(S_AXIS_S2MM_1_tdata), .S_AXIS_S2MM_1_tkeep(S_AXIS_S2MM_1_tkeep),
        .S_AXIS_S2MM_1_tlast(S_AXIS_S2MM_1_tlast), .S_AXIS_S2MM_1_tready(S_AXIS_S2MM_1_tready),
        .S_AXIS_S2MM_1_tvalid(S_AXIS_S2MM_1_tvalid),
        .S_AXIS_S2MM_tdata(S_AXIS_S2MM_tdata),
        .S_AXIS_S2MM_tkeep(S_AXIS_S2MM_tkeep),
        .S_AXIS_S2MM_tlast(S_AXIS_S2MM_tlast),
        .S_AXIS_S2MM_tready(S_AXIS_S2MM_tready),
        .S_AXIS_S2MM_tvalid(S_AXIS_S2MM_tvalid),
        .aud_adc_data(aud_adc_data),
        .aud_dac_data(aud_dac_data),
        .aud_iic_scl_i(aud_iic_scl_i),
        .aud_iic_scl_o(aud_iic_scl_o),
        .aud_iic_scl_t(aud_iic_scl_t),
        .aud_iic_sda_i(aud_iic_sda_i),
        .aud_iic_sda_o(aud_iic_sda_o),
        .aud_iic_sda_t(aud_iic_sda_t),
        .aud_lrclk(aud_lrclk),
        .aud_mclk(aud_mclk),
        .aud_sclk(aud_sclk),
        .locked(locked),
        .m_axis_aud_tdata(m_axis_aud_tdata),
        .m_axis_aud_tid(m_axis_aud_tid),
        .m_axis_aud_tready(m_axis_aud_tready),
        .m_axis_aud_tvalid(m_axis_aud_tvalid),
        .peripheral_aresetn(peripheral_aresetn),
        .s_axis_aud_tdata(s_axis_aud_tdata),
        .s_axis_aud_tid(s_axis_aud_tid),
        .s_axis_aud_tready(s_axis_aud_tready),
        .s_axis_aud_tvalid(s_axis_aud_tvalid),
        .sys_clk(sys_clk),
        .lcd_bl(lcd_bl),
        .touch_reset_n(touch_reset_n),
        .lcd_pclk(lcd_pclk),
        .lcd_video_active_video(lcd_video_active_video),
        .lcd_video_data(lcd_video_data),
        .lcd_video_field(lcd_video_field),
        .lcd_video_hblank(lcd_video_hblank),
        .lcd_video_hsync(lcd_video_hsync),
        .lcd_video_vblank(lcd_video_vblank),
        .lcd_video_vsync(lcd_video_vsync));
  assign dbg_iic_scl_i = aud_iic_scl_i;
  assign dbg_iic_scl_o = scl_effective_o;
  assign dbg_iic_scl_t = scl_effective_t;
  assign dbg_iic_sda_i = aud_iic_sda_i;
  assign dbg_iic_sda_o = sda_effective_o;
  assign dbg_iic_sda_t = sda_effective_t;

  IOBUF aud_iic_scl_iobuf
       (.I(scl_effective_o),
        .IO(aud_iic_scl_io),
        .O(aud_iic_scl_i),
        .T(scl_effective_t));
  IOBUF aud_iic_sda_iobuf
       (.I(sda_effective_o),
        .IO(aud_iic_sda_io),
        .O(aud_iic_sda_i),
        .T(sda_effective_t));
endmodule
