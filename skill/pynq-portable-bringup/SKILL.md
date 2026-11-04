---
name: pynq-portable-bringup
description: Inspect portable PYNQ overlay artifacts and plan ownership, DMA arming, cache synchronization and safe shutdown for AXI DMA simple S2MM bring-up.
---

# 通用 PYNQ 部署与安全 DMA 接管

先读取 README.md 的适用范围及 references/workflow.md。此技能不预设板卡、物理地址、IP名称、业务、时钟或包长。

1. 获取当前运行环境、bit/hwh、构建清单、调用者的IP地址契约与生产者启停接口。缺少字段时标为未知，不从另一块板复制地址或增益。
2. 默认先做离线检查：`python scripts/inspect_overlay.py --root examples/offline_fixture --spec examples/offline_fixture/spec.json`。替换为真实项目路径与从可信构建记录取得的哈希后再检查真实包。脚本不下载硬件。
3. 同一时刻指定一个 Overlay/DMA 所有者；绘图、推理和服务读取结果缓存。确认目标 DMA 是 simple S2MM 且寄存器语义匹配，才考虑 assets/simple_s2mm_session.py。
4. 在生产者关闭时分配/准备缓冲、复位并启动 DMA、提交地址和长度，之后才启动生产者。只有接收完成、实际字节数正确且协议有效后，才交给业务。
5. 停止生产者并确认 DMA halted 后释放缓冲；停止超时或生产者停止失败时保留缓冲和所有者，报告 QUARANTINED。不要通过再次下载 Overlay 强行掩盖活动 DMA 的资源问题。

实际下载、时钟/寄存器修改仅在用户任务授权范围内进行。模板只有单次固定包收取流程，不可不经审阅直接替代连续采集驱动。跨时钟、SG、DMA IP类型、缓存一致性或缓冲接口不匹配时，先换适配层。

提示词入口见 references/prompts.md；验证范围与失效条件见 README.md。
