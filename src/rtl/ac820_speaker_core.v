`timescale 1ns / 1ps
// AC820: AXI-Lite-controlled metronome + I2S slave serializer.
// RX remains the sole physical BCLK/LRCLK master. No BRAM or DMA required.
// BCLK must not exceed FCLK/16. Codec samples SD on rising BCLK edges.
module ac820_speaker_core #(
    parameter integer FCLK_HZ = 50000000,
    parameter integer IIC_DIAG_VERSION = 1
)(
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 50000000" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *) input wire s_axi_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *) input wire s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR" *) input wire [7:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWREADY" *) output wire s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WREADY" *) output wire s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BRESP" *) output reg [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BVALID" *) output reg s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARADDR" *) input wire [7:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARREADY" *) output wire s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RDATA" *) output reg [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RRESP" *) output reg [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RVALID" *) output reg s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RREADY" *) input wire s_axi_rready,
    input wire aud_sclk, input wire aud_lrclk, input wire aud_locked,
    output reg dac_data,
    input wire [9:0] codec_iic_feedback,
    output reg [2:0] codec_iic_control
);
    // Register map: 00 control(run,tone,click,restart),04 period,08 meter,
    // 0C volume(0..128),10 status,14 beat count,18 frame count,1C ID,
    // 20 FCLK_HZ,24 BCLK-fall count,28 frame age,2C keepalive.
    localparam integer WATCHDOG = FCLK_HZ * 3;
    reg aw_pending, w_pending;
    reg [7:0] aw_address;
    reg [31:0] w_data;
    reg [3:0] w_strobe;
    reg [1:0] control;
    reg [31:0] period_cycles;
    reg [2:0] meter;
    reg [7:0] volume;
    reg [31:0] watchdog_count;
    reg watchdog_fault;
    wire write_fire = aw_pending && w_pending && !s_axi_bvalid;
    wire control_write = write_fire && aw_address[7:2] == 0 && w_strobe[0];
    wire click_command = control_write && w_data[2];
    wire restart_command = control_write && w_data[3];
    wire [1:0] next_control = control_write ? w_data[1:0] : control;
    wire enabled = (|control) && !watchdog_fault;
    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;
    function [31:0] merge_bytes;
        input [31:0] old_value, new_value;
        input [3:0] strobe;
        integer n;
        begin
            merge_bytes = old_value;
            for(n=0;n<4;n=n+1) if(strobe[n]) merge_bytes[n*8+:8] = new_value[n*8+:8];
        end
    endfunction
    wire [31:0] merged_period = merge_bytes(period_cycles,w_data,w_strobe);
    wire [31:0] merged_meter = merge_bytes({29'd0,meter},w_data,w_strobe);
    wire [31:0] merged_volume = merge_bytes({24'd0,volume},w_data,w_strobe);
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            aw_pending<=0;w_pending<=0;aw_address<=0;w_data<=0;w_strobe<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;
            control<=0;period_cycles<=FCLK_HZ/2;meter<=4;volume<=16;
            watchdog_count<=0;watchdog_fault<=0;codec_iic_control<=3'b111;
        end else begin
            if(s_axi_awvalid && s_axi_awready) begin aw_pending<=1;aw_address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_pending<=1;w_data<=s_axi_wdata;w_strobe<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(watchdog_count < WATCHDOG) watchdog_count<=watchdog_count+1;
            if((|control) && watchdog_count>=WATCHDOG-1) begin
                control<=0;watchdog_fault<=1;
            end
            if(write_fire) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                case(aw_address[7:2])
                    0: if(w_strobe[0]) begin control<=w_data[1:0];watchdog_count<=0;watchdog_fault<=0;end
                    1: if(merged_period>=FCLK_HZ/4 && merged_period<=FCLK_HZ*2) period_cycles<=merged_period;
                       else s_axi_bresp<=2'b10;
                    2: if(merged_meter==2 || merged_meter==3 || merged_meter==4 || merged_meter==6) meter<=merged_meter[2:0];
                       else s_axi_bresp<=2'b10;
                    3: if(merged_volume<=128) volume<=merged_volume[7:0];else s_axi_bresp<=2'b10;
                    11: if(|w_strobe) watchdog_count<=0;
                    12: if(w_strobe[0]) codec_iic_control<=w_data[2:0];
                    default: s_axi_bresp<=2'b10;
                endcase
            end
        end
    end

    (* ASYNC_REG="TRUE" *) reg [2:0] bclk_sync, lrclk_sync, lock_sync;
    reg bclk_previous;
    wire bclk_fall = bclk_previous && !bclk_sync[2];
    reg lr_previous;
    wire channel_change = bclk_fall && (lrclk_sync[2] != lr_previous);
    wire frame_start = channel_change && !lrclk_sync[2];
    reg [31:0] frame_count,bclk_count,frame_age,bclk_age;
    reg fast_clock_fault;
    wire clock_ok = lock_sync[2] && frame_count>=2 && frame_age<FCLK_HZ/20 && !fast_clock_fault;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            bclk_sync<=0;lrclk_sync<=0;lock_sync<=0;bclk_previous<=0;
            lr_previous<=0;frame_count<=0;bclk_count<=0;
            frame_age<=32'hffffffff;bclk_age<=32'hffffffff;fast_clock_fault<=0;
        end else begin
            bclk_sync<={bclk_sync[1:0],aud_sclk};bclk_previous<=bclk_sync[2];
            lrclk_sync<={lrclk_sync[1:0],aud_lrclk};
            lock_sync<={lock_sync[1:0],aud_locked};
            if(frame_age!=32'hffffffff) frame_age<=frame_age+1;
            if(bclk_age!=32'hffffffff) bclk_age<=bclk_age+1;
            if(bclk_fall) begin
                bclk_count<=bclk_count+1;bclk_age<=0;lr_previous<=lrclk_sync[2];
                if(bclk_age<15) fast_clock_fault<=1;
            end
            if(frame_start) begin frame_count<=frame_count+1;frame_age<=0;end
        end
    end

    reg [31:0] countdown,beat_count;
    reg [2:0] beat_index;
    reg was_run;
    reg [7:0] envelope;
    reg [11:0] decay_divider;
    reg [23:0] phase;
    reg accent;
    wire starting = control[0] && !was_run;
    wire beat_event = control[0] && (starting || restart_command || countdown==0);
    localparam [23:0] PHASE_LOW = (64'd900*16777216 + FCLK_HZ/2)/FCLK_HZ;
    localparam [23:0] PHASE_HIGH = (64'd1400*16777216 + FCLK_HZ/2)/FCLK_HZ;
    localparam [23:0] PHASE_TEST = (64'd1000*16777216 + FCLK_HZ/2)/FCLK_HZ;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            countdown<=0;beat_count<=0;beat_index<=0;was_run<=0;
            envelope<=0;decay_divider<=0;phase<=0;accent<=1;
        end else begin
            was_run<=control[0];
            phase<=phase+(control[1]?PHASE_TEST:(accent?PHASE_HIGH:PHASE_LOW));
            decay_divider<=decay_divider+1;
            if(decay_divider==0 && envelope!=0) envelope<=envelope-1;
            if(!control[0]) countdown<=0;
            else if(countdown!=0) countdown<=countdown-1;
            if(beat_event) begin
                countdown<=period_cycles-1;beat_count<=beat_count+1;
                if(starting || restart_command) begin beat_index<=0;accent<=1;end
                else if(beat_index+1>=meter) begin beat_index<=0;accent<=1;end
                else begin beat_index<=beat_index+1;accent<=0;end
                envelope<=255;decay_divider<=0;phase<=0;
            end
            if(click_command) begin envelope<=255;decay_divider<=0;phase<=0;accent<=1;end
            if(watchdog_fault || (control_write && next_control==0 && !click_command)) envelope<=0;
        end
    end
    wire [10:0] tri_abs = phase[22] ? ~phase[21:11] : phase[21:11];
    wire signed [12:0] tri_signed = phase[23] ? -$signed({2'b0,tri_abs}) : $signed({2'b0,tri_abs});
    wire [7:0] gain = control[1] ? 8'd255 : envelope;
    wire signed [21:0] gain_product = tri_signed * $signed({1'b0,volume});
    wire signed [30:0] env_product = gain_product * $signed({1'b0,gain});
    wire signed [15:0] scaled_pcm = env_product >>> 12;
    wire signed [15:0] live_pcm = clock_ok && (enabled || envelope!=0) && !watchdog_fault ? scaled_pcm : 16'sd0;
    reg [15:0] stereo_sample,shift_register;
    reg [4:0] bits_remaining;
    // One I2S delay bit. At LR transition retain the previous slot's last bit,
    // then load the new word; next falling edge emits its MSB. Supports 16/32-bit slots.
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            dac_data<=0;stereo_sample<=0;shift_register<=0;bits_remaining<=0;
        end else if(bclk_fall) begin
            if(bits_remaining!=0) begin
                dac_data<=shift_register[15];
                shift_register<={shift_register[14:0],1'b0};bits_remaining<=bits_remaining-1;
            end else dac_data<=0;
            if(channel_change) begin
                if(!lrclk_sync[2]) begin
                    stereo_sample<=live_pcm;shift_register<=live_pcm;
                end else shift_register<=stereo_sample;
                bits_remaining<=16;
            end
        end
    end
    // Asynchronous pad feedback and PS IIC levels. Only meta is false-pathed.
    (* ASYNC_REG="TRUE" *) reg [9:0] codec_iic_meta, codec_iic_sync;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin codec_iic_meta<=0;codec_iic_sync<=0;end
        else begin codec_iic_meta<=codec_iic_feedback;codec_iic_sync<=codec_iic_meta;end
    end
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;end
        else begin
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;
                case(s_axi_araddr[7:2])
                    0:s_axi_rdata<={30'd0,control};
                    1:s_axi_rdata<=period_cycles;
                    2:s_axi_rdata<={29'd0,meter};
                    3:s_axi_rdata<={24'd0,volume};
                    4:s_axi_rdata<={20'd0,fast_clock_fault,watchdog_fault,clock_ok,enabled,5'd0,beat_index};
                    5:s_axi_rdata<=beat_count;
                    6:s_axi_rdata<=frame_count;
                    7:s_axi_rdata<=32'h53504b31;
                    8:s_axi_rdata<=FCLK_HZ;
                    9:s_axi_rdata<=bclk_count;
                    10:s_axi_rdata<=frame_age;
                    11:s_axi_rdata<=watchdog_count;
                    12:s_axi_rdata<={29'd0,codec_iic_control};
                    13:s_axi_rdata<={22'd0,codec_iic_sync};
                    14:s_axi_rdata<=32'h49494331;
                    default:begin s_axi_rdata<=0;s_axi_rresp<=2'b10;end
                endcase
            end
        end
    end
endmodule
