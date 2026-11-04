# 基于FPGA与ARM协同的智能音乐分析终端

正式运行软件为20261101-R6，提交归档为20261104。硬件采用AC820、XC7Z020CLG484-2、ES8388及LCD/GT911触摸屏，音频采样率为16kHz。

PL完成I2S接收、双路加窗/FFT/频谱处理和DMA传输。PS/PYNQ完成音高检测、音符事件、乐器分类、律动频谱适配和触摸界面绘制。硬件节拍模块经ES8388 DAC与LINE OUT输出节拍声音。

## 目录

| 目录 | 内容 | 入口 |
|---|---|---|
| src | RTL、约束、BD/IP配置、PS Python/C及模型依赖 | src/readme.md |
| build | 可复现构建脚本、资源/时序报告、构建记录 | build/scripts/rebuild.py |
| board | 配套bit/hwh、R6运行文件、启动Notebook和环境说明 | board/START_LCD.ipynb |
| sim | RTL/主机验证代码、夹具与结果 | sim/scripts/run_validation.py |
| data | 测试音频、标签、参考结果与分类回放 | data/README.md |
| skill | 四项可复用技能及验证记录 | skill/README.md |
| report | 大模型协作案例、原文摘录和证据索引 | report/README.md |

## 运行环境与连接

板端使用厂商AC820 PYNQ 2.7.0镜像，Python 3.8.2、NumPy 1.20.3、Pillow 7.0.0和Linux 5.4.0-xilinx-v2020.2。实际环境与镜像标识见board/environment。

将电脑音频输出接至板卡LINE IN，LCD和GT911通过配套排线连接，LINE OUT连接有源音箱。板卡与电脑连接同一局域网。浏览器访问 `http://实际IP:9090`，厂商镜像默认密码为 `xilinx`。

## 板端启动

1. 烧录配套SD镜像并启动开发板，将整个music_analysis_terminal目录上传到板端。
2. 结束已有运行会话并重启Jupyter内核。
3. 从Jupyter文件列表打开 `board/START_LCD.ipynb`，按顺序执行全部单元格。
4. LCD界面显示后输入声音，通过触摸切换页面并操作节拍器。

也可在Notebook中进入实际上传目录后运行。以下路径是示例，需与板端文件位置一致。

```python
%cd /home/xilinx/music_analysis_terminal/board/runtime
%run run_live_system.py --check-only
%run run_live_system.py --input line --ui-stats
```

`--input line` 是电脑音频线输入的默认配置。`--input vitis` 用于复现原高增益配置。`--piano-review` 为可选钢琴复核，默认关闭，使用时在启动命令末尾追加。钢琴支持判定默认开启。测试记录应保留实际启动参数。

正常结束时在Notebook选择Kernel → Interrupt，等待程序保存结果。运行期间生成的音符和分类记录位于 `board/runtime/music_records`。

## 文件校验

在电脑的工程根目录执行以下命令。

```powershell
python -B build/scripts/verify_release.py
```

出现 `RELEASE_VERIFY_OK` 表示当前发布清单、运行包和配套制品检查通过。`release_manifest.json` 对应本目录的实际文件，`board/runtime/manifest_board.json` 对应冻结的R6运行包。

## 从源码构建PL

安装Vivado 2020.2及Zynq-7000器件支持，将工程放在短英文路径。下面的工具路径需替换为本机实际安装位置，输出目录使用尚不存在的新目录。

```powershell
$env:MUSIC_VIVADO_ROOT = 'D:\Xilinx\Vivado\2020.2'
python -B build/scripts/rebuild.py --create-only --out D:/music_create_01
python -B build/scripts/rebuild.py --out D:/music_build_01 --jobs 4
```

工程创建完成会输出 `CREATE_PROJECT_OK`，生成的Vivado工程位于 `D:/music_create_01/project/audio_merged.xpr`。完整构建完成会输出 `REBUILD_OK`，在 `D:/music_build_01` 下生成project工程、artifacts中的bit/hwh/xsa、reports中的综合/实现/时序/DRC报告，以及build_receipt.json。

正式运行制品对应报告位于 `build/reports/frozen_20261031`，20261104独立重建记录位于 `build/reports/rebuild_20261104`。构建输出由 `--out` 指定，正式运行文件位于 `board/runtime`。

## 编译PS原生算法库

安装Vivado/Vitis 2020.2，把以下编译器路径改为实际位置。

```powershell
python -B build/scripts/build_native.py --host-cc D:/Xilinx/Vivado/2020.2/tps/mingw/6.2.0/win64.o/nt/bin/gcc.exe --arm-cc D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe --out D:/music_native_01
```

输出包括主机测试库 `libmusic_ps_host.dll`、ARM库 `libmusic_ps_arm.so` 和编译记录。板端启动采用随运行包配套的 `board/runtime/dsp/libmusic_ps.so`。

## 验证与测试结果

PC安装Python及NumPy后，在工程根目录执行。输出目录使用新的名称。

```powershell
python -B sim/scripts/run_validation.py --out sim/results/host_replay01
python -B sim/scripts/run_rtl.py --vivado-root D:/Xilinx/Vivado/2020.2 --out sim/results/rtl_replay01
python -B data/verify_reference_audio.py
python -B skill/tests/verify_skill_package.py
```

主机检查覆盖Python/C处理、包格式、BFP/log-mel和段组装，RTL测试台覆盖完整谱、背压与模型帧协议。

验收音频位于 `data/audio/acceptance`，依次播放pure_500_1000.wav、scale_c4_a4.wav、repeat_c4.wav，参考标签位于 `data/labels/acceptance/expected.csv`。进入板端runtime目录后，可使用以下命令采集新一轮运行。

```python
%run ../scripts/collect_acceptance.py --runtime . --case new_case01 --input line --no-feature-recording --note "PC_volume=100; pure-scale-repeat"
```

每轮使用新的case名称，等待 `ACCEPTANCE_SAVED` 后收集输出。既有实测位于 `board/results/current_r6`。

分类回放材料位于 `data/classification_r6`，包含221条音频及标签、运行文件、逐段/逐文件结果和复现脚本。进入该目录按其README安装PC依赖，执行 `python -B scripts/evaluate_r6.py --out results/replay02`。按每秒分段和非静音段多数票统计，具体配置由结果目录保存。

## 来源与依赖

设计输入来源与哈希见 `build/source_provenance.json` 和 `build/baseline`。工程RTL、PS软件及整合脚本来自团队开发与模块整合。Vivado IP及BD按AMD/Xilinx Vivado 2020.2的配置生成，板端使用厂商AC820 PYNQ镜像。环境与依赖版本见 `board/environment/environment.json`。

PYNQ、NumPy、Pillow、Python与Vivado IP遵循各自发布条件，第三方材料沿用原有许可。团队代码的开放许可由团队仓库授权声明确定。

音频来源、作者、文件标识与许可记录见 `data/provenance.md`、`data/classification_r6/source_metadata.json` 和 `data/classification_r6/data/labels/supplied_manifest.csv`。NSynth素材登记为CC BY 4.0，Iowa MIS及Wikimedia素材按逐项来源记录使用。钢琴素材还包括mcapodici/pianosounds来源，索引见data/labels/piano_iowa。现场录音由团队提供，合成输入由data/generators生成。

- Google NSynth的来源为 https://magenta.tensorflow.org/datasets/nsynth
- Iowa MIS的来源为 https://theremin.music.uiowa.edu/MIS.html
- 钢琴素材来源为 https://github.com/mcapodici/pianosounds

技能脚本和案例来源见 `skill/evidence/source_index.json` 和 `skill/extraction_process.md`，算法讨论与团队决策见 `report/ai_collaboration/README.md`。最终技术报告见 `report/technical_report.pdf`。实体钢琴后续实测合计37/49（75.5%），高音区3/5，汇总记录见 `board/results/current_r6/team_confirmed_piano_summary_20261104.json`。

## GitHub与平台交付

GitHub总工程使用本music_analysis_terminal目录，保留源码、验证、数据、技能与协作材料。平台复现代码采用单独整理的music_analysis_terminal目录，保留src、sim、build、board及发布清单。两份目录的R6正式运行制品一致，各自使用独立文件清单。

SD镜像体积约1.85GB，超出GitHub单文件限制，不在本仓库，请通过网盘另行获取：

- 文件名：`AC820_ZYNQ_Pynq_Boot_img-2.7.0.zip`
- 链接：https://pan.baidu.com/s/1XusxxofACUekKvr4DFvRVw?pwd=x2et 提取码：`x2et`

下载后按 `board/environment/image_manifest.json` 核对SHA256（`59263095d2a411241dbaacac22e856054f85690ff5ab00aa890ac6104eb27b72`），文件与哈希的对应记录见 `board/environment/image_receipt.json`。解压得到 `ACZ820_ZYNQ-2.7.0.img`。镜像是SD烧录输入，无需整份上传到板端Jupyter目录。

平台上传时，将平台目录下的整个music_analysis_terminal文件夹压缩为RAR，保留根目录层级，检查归档大小小于200,000,000字节。
