# 参考标注

`expected_events.csv` 汇总84条源音频参考记录，内容包括频率、音符、起止时间及乐器类别。

`acceptance/expected.csv` 保存三组固定输入的原始时间标注。`pitch_comparison/`、`pitch_focus/` 和 `piano_iowa/` 保存历史生成参数或播放时刻表，`nsynth_subset_metadata.json` 保存所选十条NSynth音频的原始元数据。

R6分类输入的221条逐文件标签位于 `../classification_r6/labels/expected.csv`，系统逐秒预测位于 `../../sim/results/offline_r6_20261104/segment_results.csv`。

事件时间比较以源文件标注为依据，先对齐播放器启动时刻与板端采样序号。
