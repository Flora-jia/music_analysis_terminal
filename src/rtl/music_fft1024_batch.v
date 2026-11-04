`timescale 1ns/1ps
`default_nettype none
// Training-aligned batch STFT: 16000 PCM -> 63 centered, zero-padded frames.
// Each frame is COMPLETELY captured before its header/power is sent to DMA.
// This isolates XFFT from arbitrary software/DMA backpressure.
module music_fft1024_batch (
    input wire clk, rst_n,
    input wire signed [15:0] pcm,
    input wire pcm_valid,
    output wire [31:0] m_tdata,
    output wire m_tvalid,
    input wire m_tready,
    output wire m_tlast
);
    localparam IDLE=0, START=1, READ=2, WINDOW=3, FEED=4, WAIT_FFT=5,
               HEADER=6, LOAD_POWER=7, PAYLOAD=8, RELEASE=9, GAP=10;
    reg [3:0] state;
    wire seg_ready, head_bank;
    wire [31:0] head_id, head_start, dropped;
    reg current_bank;
    reg [31:0] current_id, current_start, current_dropped;
    reg [5:0] frame;
    reg [9:0] sample_index;
    wire signed [31:0] offset=$signed({26'd0,frame})*256-512+$signed({22'd0,sample_index});
    wire in_range=(offset>=0 && offset<16000);
    wire signed [15:0] ram_data;
    music_pcm_segments segments (
        .clk(clk),.rst_n(rst_n),.pcm(pcm),.pcm_valid(pcm_valid),
        .seg_ready(seg_ready),.seg_bank(head_bank),.seg_id(head_id),.seg_start(head_start),
        .dropped_segments(dropped),.release_segment(state==RELEASE),.release_bank(current_bank),
        .read_bank(current_bank),.read_offset(offset[13:0]),
        .read_enable(state==READ && in_range),.read_data(ram_data)
    );
    wire [15:0] coefficient;
    hann_coef_rom hann(.clk(clk),.addr(sample_index),.coef(coefficient));
    wire signed [32:0] product=$signed(ram_data)*$signed({1'b0,coefficient});
    reg signed [15:0] windowed;
    wire fft_input_ready, cfg_ready;
    reg cfg_valid, cfg_done;
    wire [31:0] fft_data;
    wire [7:0] fft_exp;
    wire fft_valid, fft_last;
    wire event_unexpected, event_missing;
    // Build script enables aresetn on the IP. Only one frame is in flight.
    xfft_1024 fft (
        .aclk(clk),.aresetn(rst_n),
        .s_axis_config_tdata(8'h01),.s_axis_config_tvalid(cfg_valid),.s_axis_config_tready(cfg_ready),
        .s_axis_data_tdata({16'b0,windowed}),.s_axis_data_tvalid(state==FEED),
        .s_axis_data_tready(fft_input_ready),.s_axis_data_tlast(state==FEED && sample_index==1023),
        .m_axis_data_tdata(fft_data),.m_axis_data_tuser(fft_exp),
        .m_axis_data_tvalid(fft_valid),.m_axis_data_tready(1'b1),.m_axis_data_tlast(fft_last),
        .m_axis_status_tdata(),.m_axis_status_tvalid(),.m_axis_status_tready(1'b1),
        .event_frame_started(),.event_tlast_unexpected(event_unexpected),.event_tlast_missing(event_missing),
        .event_status_channel_halt(),.event_data_in_channel_halt(),.event_data_out_channel_halt()
    );
    always @(posedge clk) begin
        if (!rst_n) begin cfg_valid<=0; cfg_done<=0; end
        else if (!cfg_done) begin
            cfg_valid<=1;
            if (cfg_valid && cfg_ready) begin cfg_valid<=0; cfg_done<=1; end
        end
    end

    wire signed [15:0] real_part=$signed(fft_data[15:0]);
    wire signed [15:0] imag_part=$signed(fft_data[31:16]);
    wire signed [31:0] real_squared=real_part*real_part;
    wire signed [31:0] imag_squared=imag_part*imag_part;
    wire [31:0] power=real_squared+imag_squared;
    (* ram_style="block" *) reg [31:0] spectrum [0:512];
    reg [9:0] fft_bin;
    reg [7:0] block_exponent;
    reg spectrum_done, frame_error;
    reg [9:0] power_index;
    reg [31:0] power_word;
    always @(posedge clk) begin
        if (fft_valid && fft_bin<513) spectrum[fft_bin]<=power;
        if (state==LOAD_POWER) power_word<=spectrum[power_index];
        if (!rst_n || state==START) begin
            fft_bin<=0; block_exponent<=0; spectrum_done<=0; frame_error<=0;
        end else begin
            if (event_unexpected || event_missing) frame_error<=1;
            if (fft_valid) begin
                if (fft_bin==0) block_exponent<=fft_exp;
                if (fft_exp!=block_exponent && fft_bin!=0) frame_error<=1;
                if (fft_last) begin
                    spectrum_done<=1;
                    if (fft_bin!=1023) frame_error<=1;
                end
                fft_bin<=fft_bin+1'b1;
            end
        end
    end
    reg [3:0] header_index;
    reg [31:0] header_word;
    always @* begin
        case (header_index)
            0: header_word=32'hA55A0402;
            1: header_word=current_id;
            2: header_word={26'b0,frame};
            3: header_word=current_start;
            4: header_word={current_dropped[15:0],14'b0,frame_error,1'b0};
            5: header_word=513;
            6: header_word=1;
            7: header_word=0; // Reserved; not an RMS measurement.
            8: header_word={24'b0,block_exponent};
            default: header_word=0;
        endcase
    end
    assign m_tvalid=(state==HEADER || state==PAYLOAD);
    assign m_tdata=(state==HEADER) ? header_word : power_word;
    assign m_tlast=(state==PAYLOAD && power_index==512);
    always @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE; current_bank<=0; current_id<=0; current_start<=0; current_dropped<=0;
            frame<=0; sample_index<=0; windowed<=0; power_index<=0; header_index<=0;
        end else begin
            case (state)
                IDLE: if (seg_ready && cfg_done) begin
                    current_bank<=head_bank; current_id<=head_id; current_start<=head_start;
                    current_dropped<=dropped; frame<=0; state<=START;
                end
                START: begin sample_index<=0; state<=READ; end
                READ: state<=WINDOW; // RAM and synchronous Hann ROM respond at this edge.
                WINDOW: begin windowed<=in_range ? product>>>15 : 16'sd0; state<=FEED; end
                FEED: if (fft_input_ready) begin
                    if (sample_index==1023) state<=WAIT_FFT;
                    else begin sample_index<=sample_index+1'b1; state<=READ; end
                end
                WAIT_FFT: if (spectrum_done) begin header_index<=0; state<=HEADER; end
                HEADER: if (m_tready) begin
                    if (header_index==8) begin power_index<=0; state<=LOAD_POWER; end
                    else header_index<=header_index+1'b1;
                end
                LOAD_POWER: state<=PAYLOAD;
                PAYLOAD: if (m_tready) begin
                    if (power_index==512) begin
                        if (frame==62) state<=RELEASE;
                        else begin frame<=frame+1'b1; state<=START; end
                    end else begin power_index<=power_index+1'b1; state<=LOAD_POWER; end
                end
                RELEASE: state<=GAP;
                GAP: state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
