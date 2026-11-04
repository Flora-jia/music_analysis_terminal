# DSP 数值与模型特征对齐

**适用范围**：定点FFT、幅度/功率、BFP与机器学习预处理对齐；也可只使用数组比较器核对图像/其他数值特征。BFP与log-mel函数各有明确前提，不适用于任意FFT格式。

**使用方法**：在 references/contract_template.md 中填清格式和训练口径；逐层保存同源输入和参考。运行数组比较：

```bash
python scripts/check_features.py --actual examples/actual.npy --expected examples/expected.npy --atol 1e-6
```

脚本函数 restore_bfp(raw,exponents,fractional_bits) 只用于“指数表示幅度右移、功率为无符号整数”的实现；logmel(power,matrix,range_db) 以全段最大dB为参考。示例数组为小尺寸合成夹具，不是训练样本。

**来源**：集成时必须确认STFT/center/pad、Hann、mel htk/norm、dB到[0,1]映射与63帧约定；若只传功率而遗漏BFP指数，会把缩放误差传入模型。历史出现“PC同特征结果一致，但现场分类仍差”，因此把数值一致与泛化效果分开。

**已验证效果**：历史同段功率重算mel最大差为0，部分同mel的PC/板端概率最大差约1.79e-7；只证明对应阶段的软件回放一致。当前通用脚本验证无符号大值、指数平方尺度、全段归一化、形状/NaN/容差处理，及静音经最大值归一化可能变满值的边界。没有重新执行模型支路板测，也未证明新音色准确率。

**失效条件**：训练参数/矩阵不明、相位丢失后要求还原PCM、输入已是恢复功率却再次补指数、不同分帧比较、把幅度当功率、按帧归一化替代全段参考等，都需先修正契约。没有独立测试集时不报告总体准确率。
