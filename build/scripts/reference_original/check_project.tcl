set root [file normalize [file dirname [info script]]]
open_project [file join $root project audio_merged.xpr]
set tops [get_files -quiet */audio_top.v]
if {[llength $tops] != 1} {error "Expected exactly one registered audio_top.v"}
if {[get_files -quiet */pcm_dma_packetizer.v] ne ""} {error "PCM1 is still registered"}
if {[get_files -quiet */lcd_display.xdc] ne ""} {error "Retired XDC is still registered"}
foreach name {audio_top.v Audio_iic_debug_wrapper.v ac820_speaker_core.v music_fft1024_batch.v music_pcm_segments.v hann_coef_rom.v pcm_overlap_buffer.v spectrum_frame_pack.v axis_hann4096.v hann4096_rom.v} {
    set f [get_files -quiet */$name]
    if {[llength $f] != 1 || ![file isfile $f]} {error "Missing/ambiguous registered source $name"}
}
if {[llength [get_files -quiet */ac820_speaker_core.v]] != 1} {error "Expected one speaker core"}
open_bd_design [get_files */Audio.bd]
validate_bd_design
if {[get_property CONFIG.POLARITY [get_bd_ports model_dma_resetn]] ne "ACTIVE_LOW"} {error "Model DMA reset polarity mismatch"}
update_compile_order -fileset sources_1
check_syntax -fileset sources_1
puts "MERGED_PROJECT_REOPEN_OK: unique top, frozen source files, one active XDC, validated BD."
close_project
open_checkpoint [file join $root project audio_merged.runs impl_1 audio_top_routed.dcp]
report_utilization -file [file join $root reports resources.rpt]
close_design
