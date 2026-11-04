`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// fir_audio : I2S Receiver AXI-Stream -> FIR Compiler
//
// Bit-width alignment (per PG308 I2S Receiver):
//   m_axis_aud_tdata[27:12] = 16-bit audio sample (C_DWIDTH=16, MSB at bit 27).
//   FIR input is 24-bit, so left-justify the 16-bit sample into [23:8].
//
// NOTE: FIR Compiler is Non-Blocking -> output has NO m_axis_data_tready.
//       Only the input side has s_axis_data_tready (backpressure to I2S RX).
//////////////////////////////////////////////////////////////////////////////////

module fir_audio (
    input  wire        clk,
    // input: I2S Receiver 32-bit AXI-Stream
    input  wire [31:0] s_tdata,
    input  wire        s_tvalid,
    output wire        s_tready,   // backpressure to I2S Receiver (input side)
    // FIR output 24-bit (Non-Blocking: no output tready)
    output wire [23:0] m_tdata,
    output wire        m_tvalid
);

    wire [23:0] conv_tdata;
    wire        conv_tvalid;
    wire        conv_tready;

    // EXPERIMENT: try [31:16] (assume sample is in the highest 16 bits)
    // 16-bit sample [31:16] -> 24-bit left-justified [23:8]
//    assign conv_tdata  = {s_tdata[31:16], 8'b0};
    assign conv_tdata  = {s_tdata[27:12], 8'b0};
    assign conv_tvalid = s_tvalid;
    assign s_tready    = conv_tready;

    // FIR Compiler IP (Non-Blocking output)
    // 注：本 IP 变体未生成 config 通道端口（Synth 8-448 实证，C_CONFIG_TDATA_WIDTH=1
    // 表示 config 未启用而非宽度为 1）。系数固化于 IP 内部，数据通道独立工作。
    fir_compiler_audio u_fir (
        .aclk                (clk),
        .aclken              (1'b1),
        .s_axis_data_tvalid  (conv_tvalid),
        .s_axis_data_tready  (conv_tready),
        .s_axis_data_tdata   (conv_tdata),
        .m_axis_data_tvalid  (m_tvalid),
        .m_axis_data_tdata   (m_tdata)
    );

endmodule
