`timescale 1ns/1ps
`default_nettype none
// Two owned banks. A full bank cannot be overwritten; if neither bank is free,
// discard a WHOLE segment, count the gap, and resume only at a segment boundary.
module music_pcm_segments #(
    parameter integer SEG=16000,
    parameter integer AW=14
)(
    input wire clk, rst_n,
    input wire signed [15:0] pcm,
    input wire pcm_valid,
    output wire seg_ready,
    output wire seg_bank,
    output wire [31:0] seg_id, seg_start,
    output reg [31:0] dropped_segments,
    input wire release_segment, release_bank,
    input wire read_bank,
    input wire [AW-1:0] read_offset,
    input wire read_enable,
    output reg signed [15:0] read_data
);
    (* ram_style="block" *) reg [15:0] memory [0:(2<<AW)-1];
    reg [1:0] full;
    reg wr_bank, wr_active;
    reg [AW-1:0] wr_offset;
    reg [31:0] total, next_id;
    reg [31:0] ids [0:1];
    reg [31:0] starts [0:1];
    wire release0=release_segment && !release_bank;
    wire release1=release_segment && release_bank;
    wire signed [31:0] order_delta=ids[0]-ids[1];
    assign seg_ready=|full;
    assign seg_bank=full[0] && full[1] ? !order_delta[31] : !full[0];
    assign seg_id=ids[seg_bank];
    assign seg_start=starts[seg_bank];
    always @(posedge clk) begin
        if (rst_n && pcm_valid && wr_active)
            memory[{wr_bank,wr_offset}]<=pcm;
        if (read_enable) read_data<=$signed(memory[{read_bank,read_offset}]);
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            full<=0; wr_bank<=0; wr_active<=1; wr_offset<=0;
            total<=0; next_id<=0; dropped_segments<=0;
            ids[0]<=0; ids[1]<=0; starts[0]<=0; starts[1]<=0;
        end else begin
            if (release_segment) full[release_bank]<=0;
            if (pcm_valid) begin
                total<=total+1'b1;
                if (wr_offset==SEG-1) begin
                    wr_offset<=0;
                    next_id<=next_id+1'b1;
                    if (wr_active) begin
                        full[wr_bank]<=1;
                        ids[wr_bank]<=next_id;
                        starts[wr_bank]<=total+1'b1-SEG;
                        if (!full[wr_bank^1'b1] || (release_segment && release_bank!=wr_bank)) begin
                            wr_bank<=wr_bank^1'b1;
                            wr_active<=1;
                        end else wr_active<=0;
                    end else begin
                        dropped_segments<=dropped_segments+1'b1;
                        if (!full[0] || release0) begin wr_bank<=0; wr_active<=1; end
                        else if (!full[1] || release1) begin wr_bank<=1; wr_active<=1; end
                    end
                end else wr_offset<=wr_offset+1'b1;
            end
        end
    end
endmodule
`default_nettype wire
