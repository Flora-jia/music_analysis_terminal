# 乐器特征采集与诊断

本功能只增加记录，不训练模型、不修改现有分类决策、不改 PL/bit。默认关闭；通过 --capture-label 开启。屏幕和 C 音符链路继续运行。

## 直接操作

上传最新完整 audio_three_in_one_bundle.zip，解压覆盖 three_in_one。停止旧程序后重启 Jupyter 内核，在该目录运行：

```python
%run run_live_system.py --capture-label piano --capture-limit 120 --capture-note "take01; mic=实际型号; distance=实际距离; gain=实际设置; low-mid-high; soft-medium-loud"
```

如果一直使用原 Vitis 输入接法，在同一命令末尾追加 --input vitis，不要在采集期间改输入或增益。

终端会打印 CAPTURE_DIR: 后的实际目录。每次启动自动生成独立 epoch，不覆盖已有录音。一个运行只使用一个人工标签；同一轮不要混弹其他乐器或混入说话。120 指最多保存120个已推理段，不保证恰好120秒；达到上限后采集系统继续运行。

钢琴测试建议：静音两秒，依次演奏低/中/高音、轻/中/重力度、重复音及短旋律，记录实际操作。静音段也保存，但不会列入原三类训练候选。不要开启会被麦克风录到的外放节拍器。

完成后中断运行单元格，等 CAPTURE_FINAL 打印完成，再新建单元格。将下方 <epoch> 替换为 CAPTURE_DIR 中实际生成的文件夹名：

```python
%run summarize_capture.py "instrument_captures/<epoch>" --verify --export piano_take01.zip
```

在 Jupyter 文件页下载 piano_take01.zip。报告 JSON 和 CSV 同时位于该 epoch 目录，可直接查看。

其他采集标签：guitar、violin、silence、background、unlabeled。换标签需要正常停止再运行；不要直接重启仍在采集的内核。--capture-dir 可以指定输出父目录，--capture-max-mb 默认256，默认待写队列4段。需要两三种距离/增益时分别开新轮次，并在 capture-note 中记录。元数据记录软件输入配置与初始化结果；软件无法自动测量麦克风位置、外部放大器旋钮或 PCM 削顶。

## 每段保存内容

- segment_XXXXXX.npz：power(float64,513×63)，按 BFP 指数还原后的功率；mel(float32,64×63)，模型实际输入；exponents(uint8,63)。
- segments.jsonl：人工真实标签、原始三类概率、top1/top2差值、概率熵、参考标签/相似度/差距、Mel 分布统计、功率统计、估计输入强度、段号/采样窗口/epoch、推理与排队时间、模型队列丢段。
- manifest.json：特征定义、模型/Mel矩阵/参考库/硬件及相关源文件哈希、输入配置、人工备注、采集容量和写盘结果。

这些数据是功率和特征，不含相位，不能还原原始 PCM 或准确判断 PCM 削顶。关闭时音符原始 JSON 仍按原逻辑另存 music_records。

## 如何判断这两个问题

diagnostic_report.json 给出：
- low_margin_segments：三类概率接近的段数；默认仅以 top1-top2 < 0.15 作诊断标记。
- high_confidence_wrong_segments：人工标签与最高概率不符且概率 >= 0.8 的段数。
- confusion：本次人工标签到原始预测的计数。
- label_transitions/adjacent_pairs：相邻连续有效预测之间的切换，不跨段号缺口。
- accuracy：仅本轮有标签、非静音、无 gap 候选段的比例，不代表模型总体准确率。
- capture_status：保存成功、队列满丢记录、磁盘写失败、容量上限等。

0.15/0.8 仅为诊断划分，不是已经校准的拒判阈值，本轮不改变实际分类。CSV 可逐段对照演奏记录，确认是尾音、音区还是力度引发误判。

NPZ 的 Mel 可直接用于重现本机输入；power 可使用同一 mel_matrix.npy 重新计算，与保存的 Mel 对比。--verify 校验文件哈希/形状/数值并检查功率重算的 Mel 一致性（矩阵哈希不匹配会拒绝验证）。

## 数据完整性与后续训练

只记录已有 DMA1 推理消费的完整段，没有第二个 DMA 读者。推理前已被队列丢弃的段不在样本中，其数量保留；独立写盘队列跟不上会丢记录并计数。磁盘错误会停用记录并在 instrument.feature_capture / CAPTURE_FINAL / manifest 中报错，原音符和推理继续。

状态可查看 http://192.168.2.99:5002/api/instrument，重点查看 diagnostics 和 feature_capture。写盘错误时不要把本轮当成完整数据集。

先保留未经平滑的输出，便于比较修改前后的效果。训练标签来自人工 --capture-label，不使用模型预测自我标注。training_eligible_three_class 只是初筛：仍需人工排除讲话、混合声音、错误标签等污染。

训练/验证/测试按整个 epoch 或更严格的独立录音批次分组，不能随机拆相邻一秒片段。只采钢琴足够排查钢琴误判，但要更新三分类模型，还需平衡的吉他/小提琴及独立测试批次。silence/background 当前不会自动加入原三类训练。
