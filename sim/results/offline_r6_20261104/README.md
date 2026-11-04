# R6实际离线回放结果

本目录保存2026-11-04执行的R6音频离线回放，输入221条，按字节内容去重185条，共2154个一秒分析段。实际使用R6权重，钢琴支持开启，`piano-review`关闭，模型和代码哈希见 `run_manifest.json`。

`file_results.csv`、`segment_results.csv`、`suite_summary.csv` 和 `summary.json` 分别提供逐文件、逐秒、分组和机器可读汇总。Excel提供相同数据的筛选视图。`checks.json` 保存计数、概率、投票和内容哈希核对。

输入及参考标签见 `data/classification_r6/README.md`。从工程根目录运行 `python -B sim/scripts/evaluate_r6_audio.py --out sim/results/r6_replay01` 生成新一轮结果。

文件级预测采用非静音段多数票，平票记为 `tie`。结果表保留原始CNN输出和R6规则输出。主机计算耗时按PC运行环境记录。
