---
name: build-evidence-review
description: Audit build receipts and Vivado timing summaries while distinguishing constrained slack, missing constraints, rebuild evidence and measured performance.
---

# 构建制品与时序证据核查

核查资料时先分清设计参数、工具报告、主机回放、分阶段上板、最终整机实测五种证据。每项结论绑定输入/代码/bit/hwh/模型版本和测试条件，不用旧阶段结果替代新整机。

运行 `python scripts/audit_build.py --root examples/complete --spec examples/complete/receipt.json` 检查配套文件哈希及Vivado文本时序表。缺表或未知格式要报未解析；正WNS/WHS与no_input_delay/no_output_delay等约束覆盖分开报告。没有完整约束就不输出“所有板级时序均通过”。

脚本读到某个bit和报告的哈希一致，仅说明它们满足调用者提供的清单。清单必须来自可信的同次构建；不能先从随意拼凑的目录生成清单，再以清单证明来源正确。源码重建还需在新目录执行工具全流程，并验证行为。

bit哈希不同先分清头部时间戳与配置载荷变化；既不把所有差异解释为时间戳，也不要求所有布局布线重跑必须逐字节一致。检查Tcl/IP参数、地址/时钟和行为，再决定是否发布。

性能指标要注明采集窗、计算、排队、渲染和端到端的口径。窗口长度与帧移分开；吞吐、更新间隔、单次运算耗时不能互相替代。
