`timescale 1ns/1ps
module tb_spectrum_pack;
  reg clk=0; always #5 clk=~clk;
  reg rst_n=0,frame_start=0,sample_accept=0,fft_input_fire=0;
  reg s_valid=0,s_ready=1,s_last=0,result_valid=0,ready_enable=0;
  reg [31:0] scheduled_frame=0;
  reg [63:0] window_first=0;
  reg [15:0] magnitude=0;
  reg [11:0] bin=0;
  wire [31:0] data,dropped,sent;
  wire valid,last;
  reg ready=0;
  integer cycle=0,k,word_index=0,received=0,frame_id,output_file;
  reg held=0,held_last;
  reg [31:0] held_data,expected;
  function [15:0] mag;
    input integer b;
    begin
      case(b) 127:mag=250;128:mag=500;129:mag=200;default:mag=10;endcase
    end
  endfunction
  spectrum_frame_pack dut(
    .clk(clk),.rst_n(rst_n),.frame_start(frame_start),.sample_accept(sample_accept),
    .scheduled_frame(scheduled_frame),.source_drop(32'd0),.prepack_drop(32'd0),
    .window_first(window_first),.fft_input_fire(fft_input_fire),
    .frame_error(1'b0),.fft_overflow(1'b0),.fft_tlast_error(1'b0),
    .s_magnitude(magnitude),.s_bin(bin),.s_valid(s_valid),.s_ready(s_ready),.s_last(s_last),
    .result_valid(result_valid),.peak_bin(12'd128),.peak_mag(16'd500),.peak_left(16'd250),.peak_right(16'd200),
    .m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tready(ready),.m_axis_tlast(last),
    .dropped_frames(dropped),.sent_frames(sent));
  always @(negedge clk) begin cycle=cycle+1;ready=ready_enable && cycle%7!=0 && cycle%11!=0;end
  always @(posedge clk) if(rst_n) begin
    if(held && (!valid || data!==held_data || last!==held_last)) $fatal(1,"SPEC changed under stall");
    held=valid && !ready;held_data=data;held_last=last;
    if(valid && ready) begin
      frame_id=received<2 ? received : 3;
      case(word_index)
        0:expected=32'h53504543;1:expected=32'h00020040;2:expected=8260;
        3:expected=frame_id;4:expected=frame_id*512;5:expected=0;6:expected=16000;
        7:expected=32'h02001000;8:expected=32'h00010801;9:expected=32'h00011557;
        10:expected=0;11:expected=received<2 ? 0 : 1;
        12:expected={16'd128,16'd500};13:expected={16'd250,16'd200};
        14:expected=0;15:expected=4096;
        default:expected=((word_index-16)<<16)|mag(word_index-16);
      endcase
      if(data!==expected) $fatal(1,"SPEC frame %d word %d got %h expected %h",received,word_index,data,expected);
      if(last!==(word_index==2064)) $fatal(1,"SPEC TLAST mismatch");
      $fdisplay(output_file,"%08x",data);
      if(last) begin received=received+1;word_index=0;end else word_index=word_index+1;
    end
  end
  task capture;
    input integer id;
    begin
      @(negedge clk);scheduled_frame=id;window_first=id*512;frame_start=1;
      @(negedge clk);frame_start=0;
      for(k=0;k<4096;k=k+1) begin
        bin=k;magnitude=mag(k);s_valid=1;s_last=k==4095;sample_accept=1;fft_input_fire=1;
        @(negedge clk);
      end
      s_valid=0;s_last=0;sample_accept=0;fft_input_fire=0;
      @(negedge clk);result_valid=1;
      @(negedge clk);result_valid=0;
      repeat(3) @(negedge clk);
    end
  endtask
  initial begin
    output_file=$fopen("spectrum_packets.hex","w");
    repeat(8) @(negedge clk);rst_n=1;
    capture(0);capture(1);capture(2);
    if(dropped!==1) $fatal(1,"SPEC full banks must drop whole third frame");
    ready_enable=1;wait(received==2);repeat(5) @(negedge clk);
    capture(3);wait(received==3);repeat(5) @(negedge clk);
    if(sent!==3 || dropped!==1) $fatal(1,"SPEC counters mismatch");
    $fclose(output_file);$display("SPEC_RTL_PASS: 3 complete packets, 1 whole-frame drop, headers, bins, stalls and TLAST");$finish;
  end
  initial begin #2000000;$fatal(1,"SPEC simulation deadline");end
endmodule
