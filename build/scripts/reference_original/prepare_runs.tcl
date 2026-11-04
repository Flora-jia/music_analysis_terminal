set root [file normalize [file dirname [info script]]]
open_project [file join $root project audio_merged.xpr]
set bd [get_files */Audio.bd]
open_bd_design $bd
# Avoid an empty first item in ASSOCIATED_BUSIF on the base clock port.
set buses [get_property CONFIG.ASSOCIATED_BUSIF [get_bd_ports FCLK_CLK0]]
set buses [join [lsearch -all -inline -not -exact [split $buses :] {}] :]
set_property CONFIG.ASSOCIATED_BUSIF $buses [get_bd_ports FCLK_CLK0]
validate_bd_design
save_bd_design
set_property synth_checkpoint_mode None $bd
foreach ip [get_ips] {
    if {[get_property IS_LOCKED $ip]} {error "Locked IP: $ip"}
}
foreach name {xfft_0 cordic_translate_0 fir_compiler_audio xfft_1024} {
    set f [get_files -of_objects [get_ips $name]]
    set f [get_property IP_FILE [get_ips $name]]
    set_property generate_synth_checkpoint false [get_files $f]
}
generate_target all $bd
generate_target all [get_ips xfft_1024]
update_compile_order -fileset sources_1
check_syntax -fileset sources_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -scripts_only
puts "MERGE_RUN_SCRIPTS_READY"
close_project
