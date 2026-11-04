`timescale 1ns / 1ps
`default_nettype none

// Three elastic stages: synchronous ROM read, signed multiply, rounded output.
// Real input/output: signed 16 bit; imaginary output is always zero.
// Periodic Hann coefficients are unsigned Q1.15 in [0, 32768].
module axis_hann4096 (
    input wire clk,
    input wire rst_n,
    input wire [31:0] s_tdata,
    input wire s_tvalid,
    output wire s_tready,
    input wire s_tlast,
    output wire [31:0] m_tdata,
    output wire m_tvalid,
    input wire m_tready,
    output wire m_tlast
);
    reg [11:0] index;
    reg signed [15:0] sample0;
    wire [15:0] coefficient0;
    reg valid0, last0;
    reg signed [32:0] product1;
    reg valid1, last1;
    reg signed [15:0] data2;
    reg valid2, last2;
    wire ready2 = !valid2 || m_tready;
    wire ready1 = !valid1 || ready2;
    wire ready0 = !valid0 || ready1;
    wire signed [33:0] rounded_product =
        $signed({product1[32], product1}) + 34'sd16384;

    // ROM contents are generated explicitly; no run-directory-dependent mem path.
    hann4096_rom u_rom (
        .clk(clk), .en(s_tvalid && ready0), .address(index), .data(coefficient0)
    );

    assign s_tready = ready0 && rst_n;
    assign m_tdata = {16'd0, data2};
    assign m_tvalid = valid2;
    assign m_tlast = valid2 && last2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            index <= 0;
            sample0 <= 0; valid0 <= 0; last0 <= 0;
            product1 <= 0; valid1 <= 0; last1 <= 0;
            data2 <= 0; valid2 <= 0; last2 <= 0;
        end else begin
            if (ready0) begin
                valid0 <= s_tvalid;
                if (s_tvalid) begin
                    sample0 <= $signed(s_tdata[15:0]);
                    last0 <= s_tlast;
                    index <= s_tlast ? 12'd0 : index + 1'b1;
                end
            end
            if (ready1) begin
                valid1 <= valid0;
                if (valid0) begin
                    product1 <= sample0 * $signed({1'b0, coefficient0});
                    last1 <= last0;
                end
            end
            if (ready2) begin
                valid2 <= valid1;
                if (valid1) begin
                    // round-to-nearest, ties toward +infinity; no gain > 1.
                    data2 <= rounded_product[30:15];
                    last2 <= last1;
                end
            end
        end
    end
endmodule
`default_nettype wire
