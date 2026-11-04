`timescale 1ns / 1ps
`default_nettype none

// A non-blocking observer of the SAME CORDIC handshake as peak_search.
// Reserve a whole bank at frame_start; if none is free, discard the WHOLE
// incoming frame. DMA backpressure never propagates into the FFT/ADC path.
// V2: 16 header words + 2049 {bin[15:0], magnitude[15:0]} words = 8260 B.
module spectrum_frame_pack #(
    parameter integer FRAME_LEN = 4096,
    parameter integer POS_BINS = 2049,
    parameter integer FS_HZ = 16000,
    parameter [31:0] PROFILE = 32'h00011557
) (
    input wire clk, rst_n,
    input wire frame_start,
    input wire sample_accept,
    input wire [31:0] scheduled_frame, source_drop, prepack_drop,
    input wire [63:0] window_first,
    input wire fft_input_fire,
    input wire frame_error, fft_overflow, fft_tlast_error,
    input wire [15:0] s_magnitude,
    input wire [11:0] s_bin,
    input wire s_valid, s_ready, s_last,
    input wire result_valid,
    input wire [11:0] peak_bin,
    input wire [15:0] peak_mag, peak_left, peak_right,
    output reg [31:0] m_axis_tdata,
    output reg m_axis_tvalid,
    input wire m_axis_tready,
    output reg m_axis_tlast,
    output reg [31:0] dropped_frames,
    output reg [31:0] sent_frames
);
    localparam FREE=2'd0, FILL=2'd1, READY=2'd2, SEND=2'd3;
    localparam TX_IDLE=3'd0, TX_HEADER=3'd1, TX_READ=3'd2,
               TX_LOAD=3'd3, TX_PAYLOAD=3'd4;
    localparam integer PACKET_BYTES = (16 + POS_BINS)*4;
    reg [1:0] bank_state [0:1];
    // Separate simple dual-port BRAMs. No reset of sample memory is needed:
    // only complete frames become readable; malformed ones carry error flags.
    (* ram_style="block" *) reg [15:0] spectrum0 [0:POS_BINS-1];
    (* ram_style="block" *) reg [15:0] spectrum1 [0:POS_BINS-1];
    reg [31:0] header0 [0:15];
    reg [31:0] header1 [0:15];
    reg capture_active, capture_bank, have_bank;
    reg [31:0] current_frame, flags;
    reg [63:0] first_sample;
    reg [31:0] pcm_count, fft_count, output_count, positive_count;
    reg seen_last;
    reg [2:0] tx_state;
    reg tx_bank;
    reg [3:0] header_index;
    reg [11:0] read_index;
    reg [15:0] read0, read1;
    reg write_en0, write_en1;
    reg [11:0] write_address;
    reg [15:0] write_magnitude;
    wire spectrum_fire = s_valid && s_ready;
    wire [31:0] live_errors = {29'd0, frame_error, fft_tlast_error, fft_overflow};
    wire [31:0] sequence_errors = spectrum_fire &&
        (({20'd0,s_bin} != output_count) || (s_last != (output_count == FRAME_LEN-1)))
        ? 32'h00000008 : 32'd0;
    wire [31:0] bank_delta = header0[3] - header1[3];

    // Isolate BRAM controls from the legacy IP's asynchronous-reset registers.
    // These registers have synchronous reset; RAM address/data have no reset.
    // The one-cycle write delay is complete before a bank can be transmitted.
    always @(posedge clk) begin
        if (!rst_n) begin write_en0 <= 0; write_en1 <= 0; end
        else begin
            write_en0 <= capture_active && have_bank && !capture_bank && spectrum_fire && s_bin < POS_BINS;
            write_en1 <= capture_active && have_bank && capture_bank && spectrum_fire && s_bin < POS_BINS;
        end
        write_address <= s_bin;
        write_magnitude <= s_magnitude;
        if (write_en0) spectrum0[write_address] <= write_magnitude;
        if (write_en1) spectrum1[write_address] <= write_magnitude;
        if (tx_state == TX_READ) begin
            read0 <= spectrum0[read_index];
            read1 <= spectrum1[read_index];
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            bank_state[0] <= FREE; bank_state[1] <= FREE;
            capture_active <= 0; capture_bank <= 0; have_bank <= 0;
            current_frame <= 0; flags <= 0;
            first_sample <= 0;
            pcm_count <= 0; fft_count <= 0;
            output_count <= 0; positive_count <= 0; seen_last <= 0;
            dropped_frames <= 0; sent_frames <= 0;
            tx_state <= TX_IDLE; tx_bank <= 0; header_index <= 0; read_index <= 0;
            m_axis_tdata <= 0; m_axis_tvalid <= 0; m_axis_tlast <= 0;
        end else begin
            if (frame_start && !capture_active) begin
                capture_active <= 1; have_bank <= 0;
                current_frame <= scheduled_frame;
                pcm_count <= 0; fft_count <= 0; output_count <= 0;
                positive_count <= 0; seen_last <= 0; flags <= 0;
                first_sample <= window_first;
                if (bank_state[0] == FREE) begin
                    capture_bank <= 0; have_bank <= 1; bank_state[0] <= FILL;
                end else if (bank_state[1] == FREE) begin
                    capture_bank <= 1; have_bank <= 1; bank_state[1] <= FILL;
                end else dropped_frames <= dropped_frames + 1'b1;
            end else if (capture_active) begin
                flags <= flags | live_errors | sequence_errors | (source_drop!=0 ? 32'h20 : 0);
                if (sample_accept) begin
                    pcm_count <= pcm_count + 1'b1;
                end
                if (fft_input_fire) fft_count <= fft_count + 1'b1;
                if (spectrum_fire) begin
                    output_count <= output_count + 1'b1;
                    if (s_bin < POS_BINS) positive_count <= positive_count + 1'b1;
                    if (s_last) seen_last <= 1;
                end
                // peak_search pulses result_valid AFTER its last CORDIC transfer.
                // This freezes the peak and metadata together before publication.
                if (result_valid) begin
                    capture_active <= 0;
                    if (have_bank) begin
                        bank_state[capture_bank] <= READY;
                        if (!capture_bank) begin
                            header0[0] <= 32'h53504543;
                            header0[1] <= 32'h00020040;
                            header0[2] <= PACKET_BYTES;
                            header0[3] <= current_frame;
                            header0[4] <= first_sample[31:0];
                            header0[5] <= first_sample[63:32];
                            header0[6] <= FS_HZ;
                            header0[7] <= 32'h02001000; // hop512 / N4096
                            header0[8] <= (32'h00010000 | POS_BINS);
                            header0[9] <= PROFILE;
                            header0[10] <= flags | live_errors |
                                ((output_count != FRAME_LEN || positive_count != POS_BINS || !seen_last) ? 32'h10 : 0) |
                                ((fft_count != FRAME_LEN) ? 32'h40 : 0) |
                                ((pcm_count != FRAME_LEN) ? 32'h80 : 0);
                            header0[11] <= dropped_frames + prepack_drop;
                            header0[12] <= {4'd0, peak_bin, peak_mag};
                            header0[13] <= {peak_left, peak_right};
                            header0[14] <= source_drop;
                            header0[15] <= fft_count;
                        end else begin
                            header1[0] <= 32'h53504543;
                            header1[1] <= 32'h00020040;
                            header1[2] <= PACKET_BYTES;
                            header1[3] <= current_frame;
                            header1[4] <= first_sample[31:0];
                            header1[5] <= first_sample[63:32];
                            header1[6] <= FS_HZ;
                            header1[7] <= 32'h02001000;
                            header1[8] <= (32'h00010000 | POS_BINS);
                            header1[9] <= PROFILE;
                            header1[10] <= flags | live_errors |
                                ((output_count != FRAME_LEN || positive_count != POS_BINS || !seen_last) ? 32'h10 : 0) |
                                ((fft_count != FRAME_LEN) ? 32'h40 : 0) |
                                ((pcm_count != FRAME_LEN) ? 32'h80 : 0);
                            header1[11] <= dropped_frames + prepack_drop;
                            header1[12] <= {4'd0, peak_bin, peak_mag};
                            header1[13] <= {peak_left, peak_right};
                            header1[14] <= source_drop;
                            header1[15] <= fft_count;
                        end
                    end
                    have_bank <= 0;
                end
            end

            case (tx_state)
                TX_IDLE: begin
                    m_axis_tvalid <= 0; m_axis_tlast <= 0;
                    if (bank_state[0] == READY || bank_state[1] == READY) begin
                        // Oldest READY bank first, including frame counter wrap.
                        if (bank_state[0] == READY &&
                            (bank_state[1] != READY || bank_delta[31])) begin
                            tx_bank <= 0; bank_state[0] <= SEND;
                            m_axis_tdata <= header0[0];
                        end else begin
                            tx_bank <= 1; bank_state[1] <= SEND;
                            m_axis_tdata <= header1[0];
                        end
                        header_index <= 0; m_axis_tvalid <= 1; tx_state <= TX_HEADER;
                    end
                end
                TX_HEADER: if (m_axis_tvalid && m_axis_tready) begin
                    if (header_index == 15) begin
                        m_axis_tvalid <= 0; read_index <= 0; tx_state <= TX_READ;
                    end else begin
                        header_index <= header_index + 1'b1;
                        m_axis_tdata <= tx_bank ? header1[header_index+1'b1] : header0[header_index+1'b1];
                    end
                end
                TX_READ: tx_state <= TX_LOAD;
                TX_LOAD: begin
                    m_axis_tdata <= {4'd0, read_index, tx_bank ? read1 : read0};
                    m_axis_tvalid <= 1; m_axis_tlast <= (read_index == POS_BINS-1);
                    tx_state <= TX_PAYLOAD;
                end
                TX_PAYLOAD: if (m_axis_tvalid && m_axis_tready) begin
                    m_axis_tvalid <= 0; m_axis_tlast <= 0;
                    if (read_index == POS_BINS-1) begin
                        bank_state[tx_bank] <= FREE;
                        sent_frames <= sent_frames + 1'b1; tx_state <= TX_IDLE;
                    end else begin
                        read_index <= read_index + 1'b1; tx_state <= TX_READ;
                    end
                end
                default: tx_state <= TX_IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
