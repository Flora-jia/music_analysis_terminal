# 可复用技能包

版本：`skill-20261102-v1`。技能成果以**可运行校验脚本、可适配工程模板、结构化踩坑清单**为主，另附辅助提示词。每项同时有供人工使用的 README.md 和可由AI读取的 SKILL.md，不依赖特定AI产品。

| 技能目录 | 适用场景 | 直接复用内容 | 验证与限制 |
|---|---|---|---|
| pynq-portable-bringup | PYNQ Overlay、MMIO、AXI DMA simple S2MM部署 | 清单/HWH检查、依赖注入收包及安全停止模板 | 不绑定业务、板卡、IP名或地址；两种虚构映射和停止故障已测，尚无新板跨板实测 |
| axis-frame-validation | 固定完整帧、滑窗、背压和整帧丢弃 | 归一化帧契约、序号/bin/时间/同帧参考峰检查 | 可检测可观测的协议异常；握手仍需RTL，拼帧完整性需可辨载荷参考 |
| dsp-feature-alignment | 定点DSP及模型预处理移植 | 数组比较、无符号BFP恢复、明确口径的log-mel函数 | 格式前提必须匹配；数值一致不等于识别准确率 |
| build-evidence-review | 工程交付、报告与制品对应、性能描述 | 文件收据核对、Vivado裕量/时钟/约束缺项解析 | 清单须可信；解析不能替代完整重建、CDC/板级验收 |

每个子目录的 README.md 均包含适用范围、操作方法、失败来源、已验证效果与失效条件；SKILL.md 给出AI执行约束和资源索引。

## 陌生队伍的使用方法

1. 选择一项，先阅读其 README.md，再运行自带示例。示例中的IP映射和数组是合成夹具，不能下载到真实FPGA。
2. 将你的IP名称、地址、包长、分帧或数值格式填入自己的契约；不要照抄本队案例数值。
3. 可把该子目录复制到所用AI工具支持的技能目录，或直接把 SKILL.md 交给大模型；人工执行脚本也可，不要求安装Codex。
4. 先验证正常输入能通过，再主动注入一类已知错误，确认检查器能发现；最后才在你自己的板卡/任务验证。

测试需求：Python 3.8+；覆盖全部技能的测试需 NumPy 1.20+。HWH、帧契约、时序文本检查仅用标准库。DMA模板不导入PYNQ，真实驱动由调用者注入。

在 skill/ 根目录运行：

```bash
python -B tests/validate_layout.py
python -B tests/run_skill_tests.py --out skill_test_run01
python -B tests/replay_examples.py --out example_run01
```

输出目录必须是全新目录，避免覆盖证据。预期28项测试通过；示例回放含故意不通过的真实时序检查，此处“成功”指检查器正确拒绝了缺约束的报告。

## 验证依据与提炼文本

- [技能提炼过程](extraction_process.md)：按“观察/失败→协作修订→验证→边界→可复用参数”说明。
- [验证报告](validation_report.md)及 validation/：本次28项故障注入、CLI回放和历史数据重读；没有新增板测。
- evidence/source_index.json：原始材料来源、哈希与证据层级。历史板测、当前主机测试及尚未验证的提示词分开记录。
- examples/project_adapters/：本项目旧协议的适配例子，刻意放在通用PYNQ Skill外，避免把业务绑定带入通用技能。
- skill_manifest.json：技能包文件校验清单；`python -B tests/verify_skill_package.py` 可核对。

通用PYNQ部分可单独取用；是否获得通用Skill加分由评审认定。本次没有把更换示例IP名称当作跨板实测，也没有把新提示词宣称为已经统计验证的稳定工作流。
