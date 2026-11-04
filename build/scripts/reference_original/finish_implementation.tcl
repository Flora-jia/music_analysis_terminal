set root [file normalize [file dirname [info script]]]
source [file join $root project audio_merged.runs impl_1 audio_top.tcl]
file mkdir [file join $root reports]
file mkdir [file join $root hardware]
report_timing_summary -file [file join $root reports timing_summary.rpt]
report_utilization -hierarchical -file [file join $root reports utilization.rpt]
report_drc -file [file join $root reports drc.rpt]
report_bus_skew -file [file join $root reports bus_skew.rpt]
foreach kind {max min} {
    set p [get_timing_paths -delay_type $kind -max_paths 1]
    if {![llength $p]} {error "No constrained paths for $kind"}
    set slack [get_property SLACK [lindex $p 0]]
    puts "MERGED_TIMING_$kind=$slack"
    if {$slack < 0} {error "Merged timing $kind failed: $slack"}
}
set errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $errors]} {error "DRC errors: $errors"}
file copy -force audio_top.bit [file join $root hardware audio_merged.bit]
set hwh [file join $root project audio_merged.gen sources_1 bd Audio hw_handoff Audio.hwh]
if {![file isfile $hwh]} {set hwh [file join $root project audio_merged.srcs sources_1 bd Audio hw_handoff Audio.hwh]}
if {![file isfile $hwh]} {error "Missing HWH for the merged BD"}
file copy -force $hwh [file join $root hardware audio_merged.hwh]
puts "THREE_IN_ONE_BUILD_OK: exported timing-checked bit/HWH pair."
