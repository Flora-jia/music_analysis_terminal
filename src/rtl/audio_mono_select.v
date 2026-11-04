`timescale 1ns/1ps
`default_nettype none

// Select one complete RX AXI-Stream channel before the single-channel FIR.
// Unselected channels are consumed regardless of downstream readiness.
module audio_mono_select #(
    parameter [2:0] SELECT_TID = 3'd0
) (
    input  wire [31:0] s_tdata,
    input  wire [2:0]  s_tid,
    input  wire        s_tvalid,
    output wire        s_tready,
    output wire [31:0] m_tdata,
    output wire        m_tvalid,
    input  wire        m_tready,
    output wire signed [15:0] raw_pcm,
    output wire        rx_fire,
    output wire        selected_pcm_fire
);
    wire channel_selected = (s_tid == SELECT_TID);
    assign m_tdata = s_tdata;
    assign m_tvalid = s_tvalid && channel_selected;
    assign s_tready = channel_selected ? m_tready : 1'b1;
    // PG308: a 16-bit sample occupies RX TDATA[27:12].
    assign raw_pcm = $signed(s_tdata[27:12]);
    assign rx_fire = s_tvalid && s_tready;
    assign selected_pcm_fire = m_tvalid && m_tready;
endmodule

`default_nettype wire
