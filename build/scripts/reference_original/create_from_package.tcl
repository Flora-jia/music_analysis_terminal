# Self-contained source rebuild. Inputs live outside the target project tree.
set root [file normalize [file dirname [info script]]]
set inputs [file join $root merged_inputs]
set target [file join $root project]
if {[info exists ::portable_project_dir]} {set target [file normalize $::portable_project_dir]}
if {[file exists [file join $target audio_merged.xpr]]} {error "Project already exists; run rebuild.cmd instead"}
create_project audio_merged $target -part xc7z020clg484-2
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO XPM_MEMORY} [current_project]
foreach name {ac820_speaker_core.v Audio_iic_debug_wrapper.v audio_top.v audio_capture_debug.v audio_mono_select.v fir_audio.v fir_to_fft_scale.v axis_hann4096.v hann4096_rom.v fft_peak_search.v fft_accel_wrapper.v fft_frame_controller.v audio_fft_top.v fft_spectrum_chain.v pcm_overlap_buffer.v spectrum_frame_pack.v dds_tone_source.v frame_auto_trigger.v music_fft1024_batch.v music_pcm_segments.v hann_coef_rom.v} {
    add_files -fileset sources_1 -norecurse [file join $inputs rtl $name]
}
foreach name {xfft_0 cordic_translate_0 fir_compiler_audio} {
    import_ip -files [file join $inputs base_ip $name ${name}.xci]
}
import_ip -files [file join $inputs ip xfft_1024.xcix]
set_property CONFIG.Coefficient_File [file join $inputs base_ip fir_compiler_audio fir_5k_simple_16k.coe] [get_ips fir_compiler_audio]
set_property CONFIG.aresetn true [get_ips xfft_1024]
if {[get_property CONFIG.transform_length [get_ips xfft_0]] != 4096} {error "4096 FFT config mismatch"}
if {[get_property CONFIG.scaling_options [get_ips xfft_1024]] ne "block_floating_point"} {error "1024 BFP config mismatch"}
add_files -fileset constrs_1 -norecurse [file join $inputs sys.xdc]
set_property top audio_top [get_filesets sources_1]
set_property generic {FFT_USE_DDS=0 LCD_PL_SELFTEST=0 LCD_FORCE_BACKLIGHT=1} [get_filesets sources_1]
set_property verilog_define {PL2_NO_ILA} [get_filesets sources_1]
source [file join $inputs bd Audio.tcl]
set bd [get_files */Audio.bd]
open_bd_design $bd
validate_bd_design
save_bd_design
generate_target all $bd
generate_target all [get_ips xfft_1024]
update_compile_order -fileset sources_1
check_syntax -fileset sources_1
puts "PORTABLE_PROJECT_READY"
close_project
