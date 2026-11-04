`timescale 1ns/1ps
`default_nettype none
// Single clock, non-blocking capture. RAMs deliberately have no array reset.
// frame_id is a scheduled opportunity, not a count of published DMA packets.
module pcm_overlap_buffer (
    input wire clk, rst_n,
    input wire signed [15:0] pcm_data,
    input wire pcm_valid,
    input wire launch_ready, analysis_done,
    output reg frame_start,
    output reg [31:0] frame_id,
    output reg [63:0] first_seq,
    output reg signed [15:0] replay_data,
    output reg replay_valid, replay_last,
    input wire replay_ready,
    output reg [63:0] source_count,
    output wire [31:0] source_write_drop_count,
    output reg [31:0] scheduled_count, launched_count,
    output reg [31:0] scheduler_drop_count, snapshot_copy_error_count,
    output reg [12:0] last_copy_count, last_replay_count,
    output reg [31:0] task_cycles, max_task_cycles,
    output wire [3:0] debug_state
);
    localparam IDLE=0, COPY=1, SNAP_READY=2, START=3,
               READ=4, LOAD=5, SEND=6, WAIT_RESULT=7;
    reg [3:0] state;
    (* ram_style="block" *) reg [15:0] history [0:8191];
    (* ram_style="block" *) reg [15:0] snapshot [0:4095];
    reg [15:0] history_q, snapshot_q;
    reg [12:0] copy_issue, copy_received, replay_index;
    reg copy_return_valid;
    reg [11:0] copy_return_index;
    reg copy_bad;
    wire tick=pcm_valid && source_count>=64'd4095 && source_count[8:0]==9'd511;
    wire copy_read=state==COPY && copy_issue<13'd4096;
    wire [63:0] read_seq=first_seq+copy_issue;
    wire expired=copy_read && ((source_count-read_seq>=64'd8192) ||
                    (pcm_valid && source_count[12:0]==read_seq[12:0]));
    assign source_write_drop_count=32'd0; // One dedicated write port accepts every event.
    assign debug_state=state;

    // Synchronous simple dual-port RAM templates. No async-reset BRAM controls.
    always @(posedge clk) begin
        if (rst_n && pcm_valid) history[source_count[12:0]]<=pcm_data;
        if (copy_read) history_q<=history[read_seq[12:0]];
        if (rst_n && copy_return_valid) snapshot[copy_return_index]<=history_q;
        if (state==READ) snapshot_q<=snapshot[replay_index[11:0]];
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE; source_count<=0; frame_id<=0; first_seq<=0;
            scheduled_count<=0; launched_count<=0; scheduler_drop_count<=0;
            snapshot_copy_error_count<=0; copy_issue<=0; copy_received<=0;
            copy_return_valid<=0; copy_return_index<=0; copy_bad<=0;
            replay_index<=0; replay_data<=0; replay_valid<=0; replay_last<=0;
            frame_start<=0; last_copy_count<=0; last_replay_count<=0;
            task_cycles<=0; max_task_cycles<=0;
        end else begin
            frame_start<=0;
            copy_return_valid<=copy_read;
            if (pcm_valid) source_count<=source_count+64'd1;
            if (state!=IDLE) task_cycles<=task_cycles+1'b1;
            if (tick) begin
                scheduled_count<=scheduled_count+1'b1;
                if (state==IDLE && launch_ready) begin
                    frame_id<=scheduled_count;
                    first_seq<=source_count-64'd4095;
                    copy_issue<=0; copy_received<=0; copy_bad<=0;
                    last_copy_count<=0; last_replay_count<=0;
                    task_cycles<=0; state<=COPY;
                end else scheduler_drop_count<=scheduler_drop_count+1'b1;
            end
            case (state)
                COPY: begin
                    if (copy_read) begin
                        copy_issue<=copy_issue+1'b1;
                        copy_return_index<=copy_issue[11:0];
                        if (expired) copy_bad<=1;
                    end
                    if (copy_return_valid) begin
                        copy_received<=copy_received+1'b1;
                        if (copy_received==4095) begin
                            last_copy_count<=4096;
                            if (copy_bad || expired) begin
                                snapshot_copy_error_count<=snapshot_copy_error_count+1'b1;
                                state<=IDLE;
                            end else state<=SNAP_READY;
                        end
                    end
                end
                SNAP_READY: if (launch_ready) begin
                    frame_start<=1; launched_count<=launched_count+1'b1;
                    replay_index<=0; state<=START;
                end
                START: state<=READ; // Consumers accept frame_start before replay.
                READ: state<=LOAD;
                LOAD: begin
                    replay_data<=snapshot_q; replay_valid<=1;
                    replay_last<=replay_index==4095; state<=SEND;
                end
                SEND: if (replay_valid && replay_ready) begin
                    replay_valid<=0; replay_last<=0;
                    last_replay_count<=last_replay_count+1'b1;
                    if (replay_index==4095) state<=WAIT_RESULT;
                    else begin replay_index<=replay_index+1'b1; state<=READ; end
                end
                WAIT_RESULT: if (analysis_done) begin
                    if (task_cycles+1'b1>max_task_cycles) max_task_cycles<=task_cycles+1'b1;
                    state<=IDLE;
                end
                default: begin end
            endcase
        end
    end
endmodule
`default_nettype wire
