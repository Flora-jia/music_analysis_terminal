`timescale 1ns/1ps
// Control-path test only: mock XFFT does NOT verify the vendor FFT arithmetic.
module tb_fft_protocol;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0;
    reg signed [15:0] pcm=0;
    reg valid=0, ready=0;
    wire [31:0] data;
    wire out_valid, last;
    music_fft1024_batch dut(clk,rst_n,pcm,valid,data,out_valid,ready,last);
    integer cycle=0, source_index=0, count=0, frame=0, word_index=0, bin=0;
    reg held=0, held_last;
    reg [31:0] held_data;
    reg [31:0] expected;
    initial begin
        repeat(8) @(negedge clk);
        rst_n=1;
        repeat(1200000) @(negedge clk);
        $fatal(1,"Test deadline");
    end
    always @(negedge clk) begin
        if (rst_n) begin
            cycle=cycle+1;
            valid=(cycle%8==0 && source_index<16000);
            if (valid) begin pcm=(source_index%1024)-512; source_index=source_index+1; end
            ready=(cycle%7!=0 && cycle%11!=0);
        end
    end
    always @(posedge clk) if(rst_n) begin
        if (held && (!out_valid || data!==held_data || last!==held_last))
            $fatal(1,"Output changed during backpressure");
        held=out_valid && !ready;
        held_data=data; held_last=last;
        if(out_valid && ready) begin
            case(word_index)
                0: expected=32'hA55A0402;
                1: expected=0;
                2: expected=frame;
                3,4,7: expected=0;
                5: expected=513;
                6: expected=1;
                8: expected=frame%4;
                default: begin bin=word_index-9; expected=(bin+frame)*(bin+frame)+9; end
            endcase
            if(data!==expected) $fatal(1,"Frame=%0d word=%0d got=%h expected=%h",frame,word_index,data,expected);
            if(last!==(word_index==521)) $fatal(1,"TLAST mismatch");
            if(word_index==521) begin
                word_index=0; frame=frame+1;
                if(frame==63) begin
                    $display("PASS: 63 frames, centered Q15 inputs, current exponents, backpressure, TLAST");
                    $finish;
                end
            end else word_index=word_index+1;
        end
    end
endmodule

module xfft_1024(
    input aclk,aresetn,
    input [7:0] s_axis_config_tdata,
    input s_axis_config_tvalid,
    output s_axis_config_tready,
    input [31:0] s_axis_data_tdata,
    input s_axis_data_tvalid,s_axis_data_tlast,
    output s_axis_data_tready,
    output [31:0] m_axis_data_tdata,
    output [7:0] m_axis_data_tuser,
    output m_axis_data_tvalid,m_axis_data_tlast,
    input m_axis_data_tready,
    output [7:0] m_axis_status_tdata,
    output m_axis_status_tvalid,
    input m_axis_status_tready,
    output event_frame_started,event_tlast_unexpected,event_tlast_missing,
           event_status_channel_halt,event_data_in_channel_halt,event_data_out_channel_halt
);
    integer cycle=0, n=0, f=0, output_bin=0, offset=0, raw=0, product=0;
    reg outputting=0;
    reg [15:0] expected_input;
    assign s_axis_config_tready=1;
    assign s_axis_data_tready=!outputting && cycle%5!=0;
    assign m_axis_data_tvalid=outputting;
    wire [15:0] re_part=output_bin+f;
    assign m_axis_data_tdata={16'd3,re_part};
    assign m_axis_data_tuser=f%4;
    assign m_axis_data_tlast=outputting && output_bin==1023;
    assign m_axis_status_tdata=0;
    assign m_axis_status_tvalid=0;
    assign event_frame_started=0;
    assign event_tlast_unexpected=0;
    assign event_tlast_missing=0;
    assign event_status_channel_halt=0;
    assign event_data_in_channel_halt=0;
    assign event_data_out_channel_halt=0;
    always @(posedge aclk) begin
        if(!aresetn) begin cycle<=0; n<=0; f<=0; output_bin<=0; outputting<=0; end
        else begin
            cycle<=cycle+1;
            if(s_axis_data_tvalid && s_axis_data_tready) begin
                offset=f*256-512+n;
                raw=(offset>=0 && offset<16000) ? (offset%1024)-512 : 0;
                product=raw*tb_fft_protocol.dut.hann.mem[n];
                expected_input=product>>>15;
                if(s_axis_data_tdata!=={16'd0,expected_input})
                    $fatal(1,"Input sample mismatch frame=%0d n=%0d",f,n);
                if(s_axis_data_tlast!==(n==1023)) $fatal(1,"Input TLAST mismatch");
                if(n==1023) begin outputting<=1; n<=0; end else n<=n+1;
            end
            if(outputting && m_axis_data_tready) begin
                if(output_bin==1023) begin outputting<=0; output_bin<=0; f<=f+1; end
                else output_bin<=output_bin+1;
            end
        end
    end
endmodule
