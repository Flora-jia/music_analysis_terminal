# PL-2实施与验收结果

**结论：4096点窗口、hop512的连续采集、重叠分帧和完整频谱DMA链路已通过本轮离线与硬件核心验收。** 音符切分和真实乐器总体准确率不在此结论内。

日期：2026-10-30。使用用户连接的AC820、JTAG、电脑音频线。五次物理断电由用户执行并逐次确认，下载与日志核查由代理完成。正式ELF已恢复并保持运行。

## 主要结果

- 实测稳态帧率中位数 **31.244fps**，目标31.25fps；每包内部核查frame与first，first=frame×512。
- 长时间测试的已打印样本序号跨度 **649.184s**；每秒摘要累计核查 **20277包**，包错误、新增丢帧、源写入丢样均0。
- 长测后ILA：scheduler_drop/copy_error/pack_drop均0；copy/replay各4096点；累计源样本12964359。
- 最大完整PL任务周期 **24762**，按50MHz约 **0.495ms**；这不是端到端音高识别延迟。
- 同源硬件对照：从ILA取样本512…4607，按相同定点Hann重算，DMA谱最大绝对幅度差 **1.891**，容差8。
- 500Hz、E5及降低输入幅度后的强第三谐波A2、110Hz纯音，选取的稳定段YinFFT输出均为预期音名。

## 验收表

| 项目 | 结果 | 证据 |
|---|---|---|
| S1～S6、S8 | 通过：预热、逐点缓存/Hann、3次回绕、复位、背压、忙时跳过；另测每PL周期一个源事件 | simulation/overlap/，golden_windows.npz |
| S7 | 通过：停收、随机ready、半包暂停30000周期、满bank丢整帧、复位恢复 | simulation/pack/ |
| S9～S10 | 通过：实际Xilinx FFT/CORDIC模型16帧，完整点数/TLAST/bin/峰值；同源数值容差通过 | simulation/fft_integration_result.json，golden_spectra.npz |
| S11 | 通过：C/Python拒绝版本、点数、bin、flags、邻点、源丢样、64位序号异常 | simulation/protocol_v2_result.json |
| H1 | 5/5真实冷启动通过 | board/cold1…5_serial.txt、cold_boot_results.json |
| H2～H4 | 通过：真实DMA完整包、固定hop、31fps、ILA复制/回放计数与持续源写入 | long_normal_serial.txt、final_counters.csv |
| H5 | 通过，但需控制LINE IN输入幅度；高幅度A2失败样例保留 | audio_results.json、low_input_audio_results.json |
| H6 | 通过：硬件同帧PCM及软件谱对照 | matching_packet.bin、matching_pcm_and_gold.npz、ila_matching_result.json |
| H7 | 通过：1500ms暂停只丢整帧，固定hop时间轴保持 | slow_serial.txt |
| H8 | 通过：恢复后末10份摘要无新丢帧、约31fps | recovery_serial.txt |
| H9 | 已执行并记录；快音仍存在过渡错音，不作完整简谱准确率通过结论 | *_trace.csv、音高逐帧轨迹.html |
| H10 | 通过：正式ELF连续运行超过10分钟 | long_normal_serial.txt、verification.json |

## 制品与时序

配套bit/ltx/xsa/hwh位于build/，正式ELF位于software/build/audio_pl2_overlap.elf。SHA256见SHA256SUMS.txt，自动一致性检查见delivery_check.json。内部WNS=8.640ns、WHS=0.036ns，TNS/THS=0；LUT14825/53200、BRAM105.5/140、DSP19/220。新增样本RAM实测6块RAMB36，另增加独立ILA；外部音频/IIC IO约束缺项未在本轮消除。

## 仍需继续的产品工作

输入过强时存在削顶；本轮通过降低测试文件幅度恢复A2，未改Codec增益或算法。麦克风20cm仍须另测。0.15s短音的原始逐帧输出存在目标音集合外的过渡音，需要起音/切分和音符状态机；不是把更新间隔改到32ms就自动解决。

本轮没有合入PYNQ、LCD、AI分支，也未更新PC GUI。GUI后续要按first/fs或hop/fs计算时间，不能继续按每帧0.256s累加。

## 使用入口

先读README_交付与使用.md。当前电脑可在Vitis选择PL2_Overlap512 Debug配置；采用JTAG完整复位下载，无需SD卡。H9的trace ELF只用于逐帧观测，不能替换正式版本的冷启动与长测证据。回退方法也在README中。
