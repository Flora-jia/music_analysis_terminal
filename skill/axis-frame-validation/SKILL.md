---
name: axis-frame-validation
description: Validate normalized AXI Stream frame records for point order, sample timeline, same-frame reference peaks and marked whole-frame drops.
---

# 完整帧 协议与背压校验

先冻结数据契约，填写 examples/contract.json 的窗口、帧移、点数、序号和参考峰规则，再把项目原始包解码为逐包JSONL。默认全部记录必须是完整包，不能把抽样串口摘要冒充全部接收帧。

运行 `python scripts/check_frames.py --frames examples/frames.jsonl --contract examples/contract.json`。检查长度、bin顺序、有效样本数、错误位、同一 epoch 的首样本增量与帧号。需要允许整帧丢弃时在记录中显式带标记，不改写原始帧号使其看起来连续。

PL参考峰按同帧同范围同门限重算；它仅证明该规则一致，不等于基频正确。相同峰值不能排除其他频点拼帧；若要证明载荷来自正确源帧，提供逐帧可辨的 golden_values，结合源帧标记与背压测试。

故障注入包括随机 ready、半包停顿、双bank满、复位和恢复，观察 valid&&!ready 时 data/TLAST 保持、每拍只消费一次、满缓存只丢整帧。此Python脚本不能从包结果直接证明RTL握手，应同时使用项目测试台。readme中的观察层级不能合并成一次最终验收。

若跨 epoch、序号回绕或协议变长，先明确规则/解码器，再改适配层，禁止忽略异常继续拼帧。
