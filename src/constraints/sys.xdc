set_property IOSTANDARD LVCMOS33 [get_ports aud_iic_scl_io]
set_property IOSTANDARD LVCMOS33 [get_ports aud_iic_sda_io]
set_property PACKAGE_PIN G22 [get_ports aud_iic_scl_io]
set_property PACKAGE_PIN H22 [get_ports aud_iic_sda_io]
set_property IOSTANDARD LVCMOS33 [get_ports aud_mclk]
set_property PACKAGE_PIN W11 [get_ports aud_mclk]
set_property PACKAGE_PIN Y9 [get_ports sys_clk]
set_property IOSTANDARD LVCMOS33 [get_ports sys_clk]
set_property PACKAGE_PIN W10 [get_ports aud_adc_data]
set_property PACKAGE_PIN Y8 [get_ports aud_dac_data]
set_property PACKAGE_PIN U7 [get_ports aud_lrclk]
set_property PACKAGE_PIN R7 [get_ports aud_sclk]
set_property IOSTANDARD LVCMOS33 [get_ports aud_adc_data]
set_property IOSTANDARD LVCMOS33 [get_ports aud_dac_data]
set_property IOSTANDARD LVCMOS33 [get_ports aud_lrclk]
set_property IOSTANDARD LVCMOS33 [get_ports aud_sclk]

# Step 3: raw PCM, actual I2S clocks, one-second capture statistics, and DDS
# reference. Asynchronous serial/lock observations are synchronized into FCLK.
# Storage qualification can be changed in Hardware Manager.

# Explicit XDC-supported debug commands; net aliases verified against synth_1/audio_top.dcp.
# Probe vectors list bit 0 first so their numerical interpretation remains correct.
# probe0: raw_pcm[15:0]

# probe1: m_axis_aud_tid[2:0]

# probe2: m_axis_aud_tvalid

# probe3: m_axis_aud_tready

# probe4: rx_fire

# probe5: selected_pcm_fire

# probe6: aud_sclk after two FCLK synchronizer stages

# probe7: aud_lrclk after two FCLK synchronizer stages

# probe8: aud_adc_data after two FCLK synchronizer stages

# probe9: locked after two FCLK synchronizer stages

# probe10: rx_count0[31:0]

# probe11: rx_count1[31:0]

# probe12: selected_pcm_count[31:0]

# probe13: fir_valid_count[31:0]

# probe14: rx_peak0[15:0]

# probe15: rx_peak1[15:0]

# probe16: capture_window_id[31:0]

# probe17: fft_sample_data[15:0]

# probe18: fft_sample_valid

# probe19: fundamental_bin[11:0]

# probe20: fundamental_magnitude[15:0]

# probe21: result_valid

# probe22: err_frame_cnt[15:0]

# probe23: err_ovfl_cnt[15:0]

# probe24: err_tlast_cnt[15:0]

# probe25: fft_config_done

# IIC diagnostics: synchronized pad feedback, PS output and tri-state controls.
# probe26..31 = scl_i, scl_o, scl_t, sda_i, sda_o, sda_t.






# probe32 can qualify IIC capture at 2 MHz while the ILA clock stays at 50 MHz.


# PCM FIR scaling and FFT delivery diagnostics (read-only).
# probe33: fir_tdata

# probe34: fir_tvalid

# probe35: fft_sample_ready

# probe36: dbg_capture_active

# probe37: dbg_start_accepted

# probe38: dbg_fft_tvalid

# probe39: dbg_fft_tready

# probe40: dbg_fft_tlast

# probe41: dbg_fft_input_data

# probe42: dbg_frame_accept_count

# probe43: dbg_last_frame_sent

# probe44: dbg_inframe_drop_count

# probe45: dbg_gap_skip_count

# probe46: dbg_frames_done

# probe47: dbg_frame_length_error_count



# BEGIN MERGED LCD DISPLAY: original Zynq references, backlight U19
# Y8 is already aud_dac_data in sys.xdc; do not assign LCD backlight to Y8.
# Zynq LCD pins: original project_lcd/touch_ui references; backlight is U19.
# Add only AFTER the actual top module exports these exact port names.
# Touch pins are deliberately excluded until the I2C/controller allocation is resolved.
set_property PACKAGE_PIN V14  [get_ports {lcd_rgb[0]}]
set_property PACKAGE_PIN V15  [get_ports {lcd_rgb[1]}]
set_property PACKAGE_PIN V13  [get_ports {lcd_rgb[2]}]
set_property PACKAGE_PIN W13  [get_ports {lcd_rgb[3]}]
set_property PACKAGE_PIN AB15 [get_ports {lcd_rgb[4]}]
set_property PACKAGE_PIN AA21 [get_ports {lcd_rgb[5]}]
set_property PACKAGE_PIN AB22 [get_ports {lcd_rgb[6]}]
set_property PACKAGE_PIN AA22 [get_ports {lcd_rgb[7]}]
set_property PACKAGE_PIN W22  [get_ports {lcd_rgb[8]}]
set_property PACKAGE_PIN AA13 [get_ports {lcd_rgb[9]}]
set_property PACKAGE_PIN Y13  [get_ports {lcd_rgb[10]}]
set_property PACKAGE_PIN AB16 [get_ports {lcd_rgb[11]}]
set_property PACKAGE_PIN AA16 [get_ports {lcd_rgb[12]}]
set_property PACKAGE_PIN AB17 [get_ports {lcd_rgb[13]}]
set_property PACKAGE_PIN AA17 [get_ports {lcd_rgb[14]}]
set_property PACKAGE_PIN AB21 [get_ports {lcd_rgb[15]}]
set_property PACKAGE_PIN V22  [get_ports lcd_pclk]
set_property PACKAGE_PIN AB19 [get_ports lcd_de]
set_property PACKAGE_PIN AB14 [get_ports lcd_hs]
set_property PACKAGE_PIN U14  [get_ports lcd_vs]
set_property PACKAGE_PIN U19  [get_ports lcd_bl]
set_property IOSTANDARD LVCMOS33 [get_ports {lcd_rgb[*] lcd_pclk lcd_de lcd_hs lcd_vs lcd_bl}]
# END MERGED LCD DISPLAY

# BEGIN AC820 TOUCH RESET
set_property PACKAGE_PIN R15 [get_ports touch_reset_n]
set_property IOSTANDARD LVCMOS33 [get_ports touch_reset_n]
# END AC820 TOUCH RESET

# AC820_SPEAKER_CDC_BEGIN
# First asynchronous stages only; no Tcl control flow in XDC.
set_false_path -to [get_pins -of_objects [get_cells -hierarchical -regexp {.*speaker_core.*/((bclk_sync_reg|lrclk_sync_reg|lock_sync_reg)\[0\]|codec_iic_meta_reg\[[0-9]+\])$}] -filter {REF_PIN_NAME == D}]
# AC820_SPEAKER_CDC_END
