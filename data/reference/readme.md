# 软件参考与比较入口

| 入口 | 参考计算与核对内容 |
|---|---|
| `sim/scripts/run_validation.py` | BFP功率恢复、mel数值、完整段组装、原生音高与音符事件 |
| `sim/scripts/evaluate_r6_audio.py` | 1024点软件功率谱、R6分类流程与逐文件参考标签 |
| `data/labels/acceptance/expected.csv` | 500Hz/1000Hz、六音阶和三次C4的源文件时间标注 |
| `data/labels/expected_events.csv` | DSP与音符素材的84条参考记录 |
| `data/classification_r6/labels/expected.csv` | 221条音频的参考类别与内容哈希 |
| `sim/results/offline_r6_20261104/` | R6实际离线回放输出及对照结果 |

数值参考与实测输出在各自入口独立生成。帧号、源音频时间和模型哈希用于将两者对应到同一输入。
