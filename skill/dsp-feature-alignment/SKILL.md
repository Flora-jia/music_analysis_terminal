---
name: dsp-feature-alignment
description: Compare numerical DSP references and verify unsigned BFP power restoration and segment-level log-mel feature conventions.
---

# DSP 数值与模型特征对齐

要求调用者提供原始格式、符号/位宽、FFT缩放、BFP指数、窗与分帧、mel矩阵、dB参考及归一化范围。没有这些信息时，先列缺项，不用“常见默认值”补齐训练约定。

在相同PCM上分层保存窗输入、复数FFT或功率、恢复后的功率、mel、模型输入和输出。逐层确定第一处偏差，容差由定点位宽与参考算法给定，不能为了通过反复放宽。

scripts/check_features.py 提供数组比较，以及明确格式下的 unsigned BFP power 和全段最大值归一化 log-mel 函数。`restore_bfp` 假设该FFT的指数表示幅度右移，因此功率要乘2^(2e)；只在格式相符时使用。`logmel` 是一个明确的全段参考方案，不是所有模型的通用预处理。

运行示例：`python scripts/check_features.py --actual examples/actual.npy --expected examples/expected.npy --atol 1e-6`。采样率、center/pad、窗类型、帧数裁切和mel htk/norm若未以固定矩阵冻结，仍须另外核对。

数值回放一致仅证明给定输入下实现一致；不证明分类准确率、XFFT硬件精度、模拟前端或真实收音有效。归一化后的静音也可能满值，应保留独立能量门控。
