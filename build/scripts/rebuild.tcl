# Paths are relative to this release, not the original developer machine.
set release_root [file normalize [file join [file dirname [info script]] ../..]]
if {[llength $argv] != 3} {error "Expected mode output_dir jobs"}
lassign $argv mode out jobs
set out [file normalize $out]
if {[string first "2020.2" [version -short]] < 0} {error "Use Vivado 2020.2 for this frozen design"}
set inputs [file join $release_root src]
create_project audio_merged [file join $out project] -part xc7z020clg484-2
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO XPM_MEMORY} [current_project]
foreach name {ac820_speaker_core.v Audio_iic_debug_wrapper.v audio_top.v audio_capture_debug.v audio_mono_select.v fir_audio.v fir_to_fft_scale.v axis_hann4096.v hann4096_rom.v fft_peak_search.v fft_accel_wrapper.v fft_frame_controller.v audio_fft_top.v fft_spectrum_chain.v pcm_overlap_buffer.v spectrum_frame_pack.v dds_tone_source.v frame_auto_trigger.v music_fft1024_batch.v music_pcm_segments.v hann_coef_rom.v} {
    add_files -fileset sources_1 -norecurse [file join $inputs rtl $name]
}
foreach name {xfft_0 cordic_translate_0 fir_compiler_audio} {
    import_ip -files [file join $inputs ip base_ip $name ${name}.xci]
}
import_ip -files [file join $inputs ip xfft_1024.xcix]
set_property CONFIG.Coefficient_File [file join $inputs ip base_ip fir_compiler_audio fir_5k_simple_16k.coe] [get_ips fir_compiler_audio]
set_property CONFIG.aresetn true [get_ips xfft_1024]
if {[get_property CONFIG.transform_length [get_ips xfft_0]] != 4096} {error "4096 FFT mismatch"}
if {[get_property CONFIG.scaling_options [get_ips xfft_1024]] ne "block_floating_point"} {error "1024 BFP mismatch"}
add_files -fileset constrs_1 -norecurse [file join $inputs constraints sys.xdc]
set_property top audio_top [get_filesets sources_1]
set_property generic {FFT_USE_DDS=0 LCD_PL_SELFTEST=0 LCD_FORCE_BACKLIGHT=1} [get_filesets sources_1]
set_property verilog_define {PL2_NO_ILA} [get_filesets sources_1]
source [file join $inputs block_design Audio.tcl]
set bd [get_files */Audio.bd]
open_bd_design $bd
set buses [get_property CONFIG.ASSOCIATED_BUSIF [get_bd_ports FCLK_CLK0]]
set_property CONFIG.ASSOCIATED_BUSIF [join [lsearch -all -inline -not -exact [split $buses :] {}] :] [get_bd_ports FCLK_CLK0]
validate_bd_design
save_bd_design
set_property synth_checkpoint_mode None $bd
foreach ip [get_ips] {
    if {[get_property IS_LOCKED $ip]} {error "Locked IP: $ip"}
}
foreach name {xfft_0 cordic_translate_0 fir_compiler_audio xfft_1024} {
    set_property generate_synth_checkpoint false [get_files [get_property IP_FILE [get_ips $name]]]
}
generate_target all $bd
generate_target all [get_ips xfft_1024]
update_compile_order -fileset sources_1
check_syntax -fileset sources_1
file mkdir [file join $out reports]
report_ip_status -file [file join $out reports ip_status.rpt]
puts "FROZEN_CREATE_PROJECT_OK"
if {$mode eq "create"} {close_project;exit}
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis incomplete"}
open_run synth_1
report_utilization -file [file join $out reports synthesis_utilization.rpt]
close_design
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation incomplete"}
open_run impl_1
report_utilization -hierarchical -file [file join $out reports utilization.rpt]
report_timing_summary -file [file join $out reports timing_summary.rpt]
report_drc -file [file join $out reports drc.rpt]
report_bus_skew -file [file join $out reports bus_skew.rpt]
check_timing -verbose -file [file join $out reports check_timing.rpt]
foreach kind {max min} {
    set paths [get_timing_paths -delay_type $kind -max_paths 1]
    if {![llength $paths]} {error "No constrained $kind paths"}
    set slack [get_property SLACK [lindex $paths 0]]
    puts "REBUILD_TIMING_$kind=$slack"
    if {$slack<0} {error "Negative $kind timing slack"}
}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error}]]} {error "DRC errors"}
file mkdir [file join $out artifacts]
file copy -force [file join $out project audio_merged.runs impl_1 audio_top.bit] [file join $out artifacts audio_merged.bit]
set hwh [file join $out project audio_merged.gen sources_1 bd Audio hw_handoff Audio.hwh]
if {![file isfile $hwh]} {set hwh [file join $out project audio_merged.srcs sources_1 bd Audio hw_handoff Audio.hwh]}
if {![file isfile $hwh]} {error "Missing paired HWH"}
file copy -force $hwh [file join $out artifacts audio_merged.hwh]
write_hw_platform -fixed -include_bit -force -file [file join $out artifacts audio_merged.xsa]
puts "FROZEN_REBUILD_COMPLETED: outputs are a NEW build, not promoted to board/runtime"
close_project
