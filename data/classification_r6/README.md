# 最终R6模型测试数据与参考结果

测试日期为2026-11-04。使用最终提交工程的 `20261101-R6` 运行模块、原权重和参考库，钢琴支持开启，`piano-review` 关闭。

本次为PC端音频离线回放。输入功率谱由软件FFT计算，覆盖R6的功率谱到log-mel、静音门限、CNN、参考特征和默认钢琴支持流程。ADC、模拟输入增益、PL定点FFT量化、DMA及LCD共同运行的效果需使用板端实测评价。

## 阅读入口

- `outputs/r6_eval_20261104/r6_test_results.xlsx` 包含汇总、221条逐文件结果、2154条逐秒结果和参考标签。
- `results/run01/file_results.csv` 为逐文件结果，包含首秒预测、原始CNN与R6最终规则的文件投票。
- `results/run01/segment_results.csv` 为逐秒预测，保留各类概率、RMS估计、支持规则生效标记和尾段补零量。
- `results/run01/failed_files.csv` 为文件级投票与参考标签不一致的59条记录，包含平票。
- `results/run01/summary.json`、`run_manifest.json` 和 `checks.json` 保存汇总、环境、权重哈希与一致性检查。
- `data/audio/` 保存221条原音频副本，`data/labels/expected.csv` 保存其参考标签和内容哈希。
- `runtime/` 保存本次调用的冻结运行包。模型参数和运行源码受其中原清单校验。

## 测试口径

1. 参考类别沿用提供的 `测试清单.csv`。NSynth的 `string_acoustic` 按模型中的 `violin` 类别统计，其范围为弦乐家族。录音中的每秒乐器身份和静音起止尚无人工逐段标注。
2. 音频以float32读取，多声道算术平均为单声道，采用soxr_hq重采样到16kHz。保留源文件音量。
3. 从文件起点按一秒划分，帧移一秒。末尾不足一秒补零，补零量记录到每段结果。
4. 每段计算1024点周期Hann窗、256点帧移、两端常数补零的63帧单边功率谱。调用冻结 `ReferenceSession.next()` 和默认钢琴支持规则进行分类。每个独立音频内容的首段还与冻结 `mel_spectrogram_np()` 核对数值一致性。
5. 文件级结果采用所有非静音段的多数票。有多个并列最大类别时保留 `tie`，全静音时输出 `silence`。这是本次离线统计方法，LCD上显示的仍是逐段输出。
6. 首秒正确数和文件投票正确数分列。长录音中的类别跳变、静音门控和支持规则修正保留在逐秒结果。

参考标签由提供清单给定，预测由程序实际计算。源目录的 `预期结果.csv` 和示例预测属于候选模型测试口径。本次使用本包内重新生成的R6结果。

## 分组结果

| 测试组 | 文件数 | 首秒匹配参考 | 原始CNN文件投票匹配 | R6文件投票匹配 |
|---|---:|---:|---:|---:|
| NSynth三乐器音高组 | 36 | 28 | 22 | 22 |
| NSynth钢琴C2–C7 | 61 | 59 | 36 | 41 |
| NSynth吉他E2–E6 | 49 | 16 | 40 | 40 |
| NSynth弦乐G3–C7 | 42 | 39 | 32 | 32 |
| 外部真实独奏 | 3 | 2 | 3 | 3 |
| 外部真实录音 | 6 | 4 | 5 | 5 |
| 现场录音 | 13 | 1 | 9 | 10 |
| Iowa采样 | 11 | 7 | 9 | 9 |
| 含重复文件的合计 | 221 | 156 | 156 | 162 |

按字节内容去重后为185条，文件投票匹配参考140条，匹配率75.7%。此数字描述本批混合回归输入。训练、调参、录音来源重叠尚未逐项排除，且各组包含不同的录音长度和静音占比。

其中36条文件与其他组字节相同。外部独奏组又由外部录音组的三个来源裁剪或重采样得到，字节去重后仍存在来源关联。221条文件记录、185条字节唯一文件都应与独立录音数量区分。

共有23个文件发生文件级投票平票，585个一秒段被门控为静音。静音段用于反映源录音覆盖情况，文件投票仅使用非静音段。部分Iowa钢琴文件包含较长静音或衰减尾声，文件级正确也可能只基于少数有效段。

## 外部录音结果

| 文件 | 参考类别 | 首秒输出 | 文件投票输出 |
|---|---|---|---|
| guitar_solo.wav | guitar | guitar | guitar |
| piano_solo.wav | piano | piano | piano |
| violin_solo.wav | violin | guitar | violin |
| guitar_soft.wav | guitar | guitar | guitar |
| guitar_wiki.ogg | guitar | violin | violin |
| piano_greensleeves.wav | piano | piano | piano |
| piano_satie.wav | piano | piano | piano |
| violin_bach_partita.ogg | violin | piano | violin |
| violin_jazz.ogg | violin | violin | violin |

小提琴独奏首秒被判成吉他、长巴赫录音首秒被判成钢琴，随后文件投票恢复为弦乐。`guitar_wiki.ogg` 的42个非静音段均输出violin。逐秒结果能反映这些变化。

## 复现

本轮主机使用Python 3.13.14、NumPy 2.5.3、SoundFile 0.14.0、librosa 1.0.0和soxr 1.1.0。环境记录见 `results/run01/run_manifest.json`。安装依赖后从本包根目录执行。

```bash
python -m pip install -r requirements.txt
python -B scripts/evaluate_r6.py --out results/replay02
```

输出目录需为新目录。脚本直接使用本包data和runtime，不需要原D盘工作目录。正常结束时打印 `EVALUATION_COMPLETE`，同时输出新的逐文件、逐秒与分组结果。

当前冻结权重的SHA256为 `b3cfc4c092a788968e343b6b06bc678ea79d840bab59cf7c772494b948f727cf`。独立清单 `bundle_manifest.json` 记录交付内容哈希，运行 `python -B scripts/verify_bundle.py` 可核对。

## 报告可用表述

> 使用最终提交R6模型及其默认钢琴支持规则，在PC端对221条测试音频进行离线回放，共分析2154个一秒段。按非静音段多数票统计，外部独奏组为3/3，外部录音组为5/6。部分样本存在起始段误判、类别跳变及平票。各组参考标签、逐秒预测和输入哈希随测试包提供。该组结果用于模型与软件规则的离线回归，整机效果另由板端实测给出。

## 来源记录

音频来自用户提供的 `测试音频汇总`，组别包括NSynth、Wikimedia Commons、现场录音和Iowa MIS。`data/labels/supplied_manifest.csv` 保留原清单，`expected.csv` 同时保留原文件标识、音高字段和标签口径。音频内容逐字节复制，未重新编码。

原清单音名和MIDI作为提供方元数据保留。实际需要音高参考时，应优先核对MIDI与音名的一致性，例如MIDI42为F#2，MIDI43为G2。当前结果表评估乐器分类。
