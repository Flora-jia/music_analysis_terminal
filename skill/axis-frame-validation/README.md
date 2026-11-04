# 完整帧 协议与背压校验

**适用范围**：有帧号、采样时间或索引的AXI Stream/DMA固定帧；更换任务只需解码成相同JSONL契约。脚本不是通用二进制协议解析器。

**用法**：阅读 SKILL.md，填写 examples/contract.json；将真实完整包解码为sequence、first_sample、sample_count、bins、values、errors、epoch等字段。允许整帧丢弃时显式记whole_frame_drop。运行：

```bash
python scripts/check_frames.py --frames examples/frames.jsonl --contract examples/contract.json
```

**来源**：旧单峰结果不能检查其余频点；全谱改造必须保留同帧最大峰和邻点对照。旧日志出现first每帧增加4098而非4096，说明帧间有未接收样本；不能只看错误计数为零就称连续采集。慢接收会产生帧号缺口，必须区分整帧丢弃、日志抽样与真实拼帧。

**已验证效果**：历史完整谱仿真及上板记录验证包长、bin、峰值/邻点、满bank整帧丢弃和恢复；本次新通用工具以故障注入检测乱序、短包、错误hop、参考峰不一致、未标记缺口和带黄金参考的拼接数据。历史结果不表示本次又上板。

**失效条件**：协议解码错误、日志只抽样、帧号回绕未定义、重置未分epoch、参考峰规则不同、没有可辨源帧黄金数据时，不能据本工具单独证明“从未拼帧”。TLAST、valid/ready和多分支握手仍须RTL/ILA证据；同峰不等于同载荷，更不等于基频正确。

**复用模板**：references/pitfalls.md 提供从现象到最小检查的清单与提示词；examples是可修改的归一化记录，数值与本项目参数无绑定。
