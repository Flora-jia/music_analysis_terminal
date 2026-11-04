# 测试数据来源

整理日期为2026-11-04。音频由团队已有DSP调试包和测试音频汇总复制，文件内容哈希分别记录在 `audio_manifest.json` 与 `classification_r6/input_manifest.json`。复制时保留音频内容和格式。

| 数据组 | 作者或来源 | 处理及用途 |
|---|---|---|
| dsp_baseline、pitch_comparison、pitch_focus、note_events、pl2_board、acceptance | 本项目的正弦与谐波合成脚本及调试记录 | DSP、协议、音高和音符事件回归，生成代码位于generators |
| piano_iowa | University of Iowa Electronic Music Studios / Lawrence Fritts，既有素材经mcapodici/pianosounds取得 | 保留五条原Ogg、既有解码WAV、静音及两轮播放轨，逐文件来源见labels/piano_iowa |
| nsynth_guitar、nsynth_string_family | Google NSynth，Jesse Engel等，2017 | 十条原WAV及原始数据集元数据 |
| s01_nsynth_notes～s04_nsynth_strings | 团队测试汇总中的NSynth acoustic采样 | 单音、音域与乐器家族回归，原始文件编号保留于classification_r6/labels |
| s05_external_solo、s06_external_recordings | Wikimedia Commons录音及团队既有精简音轨 | 三条16kHz独奏及六条原录音，提供方来源与许可元数据保留于classification_r6/source_metadata.json |
| s07_field_recordings | 团队手机或麦克风现场录音 | 13条现场输入，原文件标识保留于标签清单 |
| s08_iowa_samples | University of Iowa Musical Instrument Samples | 十一条原始AIFF/AIF录音，包含钢琴、吉他和小提琴 |

NSynth原始家族标签和模型分类名一并保留，`string_acoustic` 采用模型的 `violin` 输出类别。文件清单中的 `byte_identical_to` 记录内容重复关系，外部独奏与原录音之间的裁剪、重采样来源关联见分组说明。数据用于按版本组织的工程回归，统计时保留来源、训练调参与重复项口径。

## 原始来源入口

- University of Iowa Musical Instrument Samples https://theremin.music.uiowa.edu/MIS.html
- 钢琴素材直接来源 https://github.com/mcapodici/pianosounds
- Google NSynth数据集 https://magenta.tensorflow.org/datasets/nsynth
- NSynth文献 https://arxiv.org/abs/1704.01279
- Wikimedia Commons逐条来源见 `classification_r6/source_metadata.json`

NSynth来源材料记录采用CC BY 4.0，Wikimedia录音按逐文件元数据分别标注公共领域、CC0、CC BY或CC BY-SA。使用条件随原始来源与元数据保留。
