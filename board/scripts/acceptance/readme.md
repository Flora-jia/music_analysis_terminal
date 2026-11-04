# 板端运行证据采集

本工具通过正式`run_live_system.py`入口采集命令、控制台和自动运行记录。默认运行目录为本工程的`board/runtime`。

## 命令行

在板端终端进入工程根目录，执行以下命令。

```bash
python3 -B board/scripts/acceptance/collect_acceptance_isolation.py --case wired_acceptance01 --input line --no-feature-recording --note "PC_volume=100; pure_scale_repeat; touch_metronome_operated"
```

参数中的note按实际声源、播放次序与操作填写。正常中断程序后，等待`ACCEPTANCE_SAVED`，采集文件位于`board/runtime/acceptance_runs/wired_acceptance01.zip`。

## Notebook

从工程根目录打开Notebook后执行。

```python
%run board/scripts/acceptance/collect_acceptance_isolation.py --case wired_acceptance02 --input line --no-feature-recording --note "PC_volume=100; pure_scale_repeat"
```

每轮case使用新的英文名称。采集工具和正式入口共用一次启动流程，采集期间由该入口管理Overlay和DMA。

## 常用参数

| 参数 | 用途 |
|---|---|
| --runtime | 显式指定另一份完整运行目录 |
| --input line | 使用最终测试采用的LINE IN配置 |
| --no-feature-recording | 保留分类推理与运行记录，关闭额外power/mel NPZ录制 |
| --capture-label piano | 记录输入声源的人工参考标签 |
| --capture-limit 120 | 设置额外特征录制上限 |
| --no-model | 运行音高和显示配置对照 |
| --headless | 运行采集分析配置对照 |
| --piano-review | 按参数显式启用钢琴复核配置 |

参考标签作为操作者元数据记录。分类预测、音符事件和统计值由系统计算生成。启用特征录制时，power/mel与段索引同目录保存。
