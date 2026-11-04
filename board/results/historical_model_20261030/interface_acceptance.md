# PL 1024 FFT + PYNQ 模型接入

**2026-10-31最新板测：暂不作为效果通过版交接。** reference_check_5cddc23e原CNN三类8/2/3，参考库5/5/9，音乐19/30，暂停0/10；40段连续无丢段。PC同特征回放一致，详见[本批评估](analysis_reference_5cddc23e.md)。活动门控候选只在能量计算排除80Hz以下，模型频谱不变，PC110音乐/30暂停均可区分，尚待新板测；新诊断[07补丁](linein_gain_gate_v1_patch.zip)用于本批三曲+18dB/0dB对照，不是正式交接包。用户指定队友基于`audio_f0923 (2)`的4096-only工程，后续必须补入完整PL1024/DMA1支路，[移植要求](../../docs/18_队友4096基线补入PL1024的对接要求.md)已记录，未修改队友工程。

当前主线（2026-10-30）：**PL 做模型所需的 1024 点 FFT**。保留原 PL 4096 点 FFT 音高支路。PS/PYNQ 接收完整功率谱、还原 BFP 尺度、计算 mel 和运行已有 NumPy CNN。PS 部署代码没有执行 FFT。

**最新任务顺序：先做一版实际效果更好的模型识别，再与队友对接。** 用户已明确先LINE IN、后麦克风，并授权CNN权重不变、增加参考库校准。当前候选为[upload_reference_v1.zip](upload_reference_v1.zip)，操作见[候选说明](reference_candidate_README.md)。70条校准参考 + 中心化余弦匹配，在三份原录音新的不重叠时段PC对照由16/60到45/60（三类9/5/2到13/13/19）；这是同录音异时段结果，不是板端或换曲准确率。下一步只运行新包06_reference_check.ipynb验证同段原CNN/参考库结果，尚不交给队友当验收版本。下文先对接的旧安排已被本条更正。

**用户最新安排：重训后置，先用现有模型合成完整工程。** 已新增[队友接入包](handoff_fixed_v1/README.md)，统一原始结果与可选显示决策接口；默认保留原预测，不启用平滑/拒识。已见80个音乐段的[固定权重诊断](analysis_fixed_model_options.md)未找到同时改善三类的统一去低频/降噪/动态范围/平滑方案。接口包通过PC检查、未板测，不能称识别质量达标。下一步以新的单音/短乐句对照及队友主程序联调为主线；数据适配重训保留第二阶段。

本目录真实音频版已完成构建，并在AC820/PYNQ2.7.0上实际运行PL频谱→mel→CNN。首轮同一小提琴10段判violin5/guitar5；后续03对照+18dB组violin10/10、0dB组violin9/10，两组均无gap/dropped。端到端已接通，整体识别质量尚未验收。当前上传目录为 `upload_live_v1`，禁止拿旧 bit 配本目录接收器。旧 `integration/music_pynq` 是未采用的 PCM 替代方案。

**最新04结果**：网易云acceptance_2a927e4d实际板测钢琴8/10、吉他2/10、小提琴1/10、暂停10/10，40段无gap/dropped。原MP3与起点已收到并完成同源PC对照：原起点平均声道6/3/0，近似对齐7/2/0，原文件未经声卡/ADC/PL已误判；本批PS回放误差≤2.3842e-7。保持1024，优先解决真实录音适配范围，不将低分直接归因FFT点数。详见[本批报告](analysis_acceptance_2a927e4d.md)。用户实际网易云100/系统64；旧04 metadata写死30已修复为运行前填写实际音量，原ZIP保留，修改Notebook未板测，无需重跑本批。此前B站批次和03保留作历史，不能混为同一输入。

**现在直接上板**：将 `upload_live_v1` 整个文件夹复制到板上Jupyter目录，进入该文件夹，打开 `01_live.ipynb`，连接原工程使用的音源，运行唯一代码格。它将校验文件、加载overlay、读回Codec、接收10个完整段并输出分类结果。结果保存为 `live_results.json`，完整控制台输出也应保留。旧DDS的v1/v2仅留作失败记录，不再等待那些窗口，也不需要再次执行构建命令。

如果使用压缩包，先在Jupyter网页上传电脑上的 `upload_live_v1.zip`。Terminal不会自动进入网页上传目录；提示符 `root@pynq:/` 表示在根目录。先执行 `find /home /root /mnt /media -type f -iname '*upload_live_v1*.zip' 2>/dev/null` 获取真实路径，cd到该文件所在目录后再运行 `python3 -m zipfile -e upload_live_v1.zip .`，解压后的文件夹与zip同级。找不到时先确认上传完成和实际文件名，不重新构建硬件。

本次两条FFT均接真实输入。布局布线后WNS=6.604ns、WHS=0.045ns；LUT=9334/53200、FF=14230/106400、BRAM=31/140、DSP=24/220。DRC无错误，仍有DSP流水级建议和供应商互连无负载网警告；原约束中1个输入、3个输出缺IO延迟。上述结果证明构建完成，不证明Codec板级时序、实际FFT数值或真实识别已通过。日志 `live_resume_v1.log` 末尾有 `BIT_READY`，报告在 `build_live_v1/`。阶段与完成状态见15号问题记录。

初次板测曾停在FCLK0门控，后续已通过加载后设置50MHz继续到实际推理。当前Notebook加载后打印PYNQ版本及实际FCLK0，在创建DMA前用Clocks.fclk0_mhz=50.0设置并再次核验；不修改CPU/DDR/PLL和启动文件，也不放宽50MHz门槛。每次重新Overlay下载后都要执行此步。原upload_live_v1.zip保留为初始交付，新增upload_live_v1_clockfix.zip使用同一bit/hwh及固定文件，仅更新Notebook；已上传原包的用户直接替换Notebook代码格即可。

**最新板测（2026-10-30收到日志）**：03对照已完成，+18dB组小提琴10/10、0dB组小提琴9/10（第6段误判吉他），单独infer_ms中位86.75/88.47ms，mel_ms中位35.30/34.56ms；两组连续无丢段，最终RX/DMA停止、PGA恢复。不要与首轮含mel的125.29ms直接比较声称加速。暂留+18dB、用户系统64/播放器30。重播非采样对齐，不能据这次10/10认定总体准确率、增益最优或FFT数值已验证。当前不改bit/模型或添加平滑。

**03特征回放已完成**：后续收到f225616e配套ZIP，power重算mel最大误差0，同mel的PC/板端概率最大误差1.78814e-7，20段标签一致，包括0dB段6误判；见[回放报告](analysis_gain_f225616e.md)。04随后也已实际上板，最新结果与下一步见本文开头。本批PS回放通过仍不等于XFFT数值或整体识别质量已验收。

## 两种 FFT 的分工

```text
ES8388/I2S -> TID0 raw PCM16（16kHz）
                ├-> 原 FIR / scale / 4096 FFT -> DMA0 -> 原音高业务
                └-> 双段缓存 / periodic Hann / 1024 FFT / 功率
                       -> DMA1 -> PYNQ BFP还原 -> mel64x63 -> NumPy CNN
```

1024 点频率间隔 15.625Hz，与已验证模型的训练特征一致；4096 点为 3.90625Hz，保留给音高分析。以后若只用 1024 做音高，需要另行验证低音区精度。模型无需改为 4096 或重新训练。

模型支路在 FIR 前取样，避免原 5kHz FIR 改变训练输入的音色。每段连续 16000 点；63 帧、hop=256、两端按该段补零，和训练的 center=True / constant 对齐。初版每个完整一秒段分类一次；不承诺当前已满足连续演奏的延迟目标。

## 源码与已有修正

- `seed/` 冻结自用户指定的 `E:/FPGA/qiansai2026/audio_f0923`，保留当前双 DMA BD 和 4096 核心；`upstream_manifest.json` 登记来源。顶层替换了有时序问题的旧 1024 批次链，原工程未修改。
- `rtl/music_pcm_segments.v` 管理两个独占段缓存。慢消费者不会被覆盖；空间不足时舍弃整段，在下一段边界恢复，并用段号/丢段计数显示缺口。
- `rtl/music_fft1024_batch.v` 明确同步 RAM/Hann 读时序，FFT 输入遵守 ready；完整收完本帧 FFT 后锁定 exponent，再发帧头和功率谱。DMA 反压期间数据保持。XFFT 构建时启用 aresetn。
- 构建脚本额外导出DMA1的 `s2mm_prmry_reset_out_n`，同时复位模型缓存/FFT和诊断DDS相位。软件复位DMA时不保留旧半帧，防止DMA预先暂存少量word导致首帧错位；该改动尚待BD验证和板测。
- `board/pl_fft.py` 每帧有限超时接收；只拼同段连续 0..62 帧；处理 uint32 功率和本帧指数。恢复公式是 `power * 2**(2*exponent) / 32768**2`。
- `board/frontend.py` 移植队友当前 C 寄存器顺序，ACKEN、7位地址、STOP+START、忙状态、错误和超时处理齐全；关键读回全部通过后才开 RX。R09=66，R16=C2。`reference/frontend_main.c` 保留移植来源。

仅首轮模型支路接入，不包含原4096 DMA接收服务、显示界面或连续原始PCM/波形输出。这些可以在接通后并行补入；本版频谱不能还原原始相位与波形。

## 1. 可选：在电脑 Vivado 2020.2 中构建DDS（当前跳过）

仅在需要隔离FFT/DMA问题时生成DDS诊断版本。脚本会自行创建工程，不需要预先执行 `create_project`。以下为旧操作示例，当前不再重复执行：

```tcl
set argv [list D:/music/music_ai/integration/fft1024_pynq/build_dds_v2 dds]
source D:/music/music_ai/integration/fft1024_pynq/build.tcl
```

脚本建立 xc7z020clg484-2 工程，将冻结输入放在工程旁边的 `build_dds_v2_inputs/`，再导入 BD/IP，开启 1024 FFT reset，综合实现并导出：

```text
build_dds_v2/delivery/music_fft.bit
build_dds_v2/delivery/music_fft.hwh
build_dds_v2/delivery/music_fft.xsa
build_dds_v2/delivery/build_mode.txt
```

`BIT_READY` 才表示脚本构建完成；有错误就保存日志，不要从旧目录找 bit 代替。脚本输出资源、时序、DRC 报告，负 setup/hold slack 会阻止交付。工程和对应的 `_inputs` 目录都必须不存在；再次构建用 v3。工程内 `frozen_inputs_path.txt` 指向同级输入快照，两个目录一起保留。也可用 `validate` 模式先创建和检查工程，不执行综合，但该模式没有交付 bit。

2026-10-28 v1 导入BD时报 `filemgmt 20-1381/20-984`：此前将源BD暂存到工程目录内部，Vivado2020.2拒绝重叠目录，后续 `get_files` 为空才出现 `open_bd_design <>`。现在改为同级输入目录，并在打开BD前检查导入结果。保留失败v1记录，关闭工程后用上述v2命令重跑，不在v1中继续 `update_compile_order`。

DDS 仅替换模型支路的输入为内部500Hz；4096支路继续真实输入。DDS 不需要 Codec 或外部音源，因此先隔离 PL/DMA 协议问题。

若工程创建或 IP 参数报错，记录完整 Tcl 输出。live流程已在本机Vivado2020.2完整执行；DDS配置尚未完成构建。尚未核对实际 PYNQ 启动平台与原 BD 的 HP0/EMIO/时钟兼容性，不用本工程 XSA 重做 FSBL 或执行 ps7_init。已有 AC820 PYNQ 能启动时先保留原启动文件。

## 2. 打包并上传

在项目根目录的电脑终端，用已有含 NumPy 的 Python：

```powershell
python integration/fft1024_pynq/package_board.py integration/fft1024_pynq/build_dds_v2/delivery integration/fft1024_pynq/upload_dds_v2
```

整个 `upload_dds_v2` 文件夹复制到板上 Jupyter 目录。保持 bit/hwh 同名，保留 models 子目录和 manifest。脚本按工程内的路径记录读取同级输入快照，生成文件 SHA-256、构建输入哈希和从冻结 RTL LUT/Hann 计算的 DDS 数值参考，不会使用历史 bit 兜底。

用户提供的 ACZ820 PYNQ 手册 PDF 第80～85页为 overlay 导出/上传参考，教程中的 GPIO 设计需换成本工程。其示例页面号不构成当前音频工程已经通过的证据。

## 3. 可选：DDS 整段验证

在板上进入上传目录，新建 Notebook。每次实验用新加载的 overlay 和唯一接收器。整格执行：

```python
from pynq import Overlay
from board_check import verify_bundle, verify_overlay, check_dds
from pl_fft import FFTReceiver

print(verify_bundle('dds'))
ol = Overlay('music_fft.bit')
print(verify_overlay(ol))
rx = FFTReceiver(timeout=3.0)
try:
    batch = rx.receive_batch()
    print(check_dds(batch))
finally:
    rx.close()
```

通过判据：收到同段完整63帧、错误标志为0，第10帧峰值 bin=32 / 500Hz，与精确 Q15 输入的软件参考功率相对误差≤0.05。打印 mel 误差及 exponent 范围；`dds_captured.npz` 保存原始结果。0.05是首版工程阈值，需结合 XFFT 实际量化结果复核，不能把对拍通过等同于真实收音或分类通过。

超时/报错后保存整格输出。先执行成功的 `rx.close()`，再重载 overlay；不要直接新建接收器从半段继续。若 close 因 DMA reset 超时失败，保留对象与缓存，不重载、不释放；重启板卡恢复后排查 PS/AXI 时钟和总线状态。

## 4. 当前主线：真实输入完整版本

当前 `build_live_v1` 已完成构建并打包，不再执行下面命令重复创建。下例仅供手动从源码复现，使用空会话和一个尚不存在的版本目录：

```tcl
set argv [list D:/music/music_ai/integration/fft1024_pynq/build_live_v2 live]
source D:/music/music_ai/integration/fft1024_pynq/build.tcl
```

以下打包已执行成功，`upload_live_v1` 已存在，不要再次运行覆盖。后续新版本改用新的交付和输出目录：

```powershell
python integration/fft1024_pynq/package_board.py integration/fft1024_pynq/build_live_v1/delivery integration/fft1024_pynq/upload_live_v1
```

将新的 `upload_live_v1` 整个目录上传并进入此目录。该版两条 FFT 都接真实音频。不要只改 build_mode.txt 冒充切换输入。

上传包带有 `01_live.ipynb`。在板上Jupyter打开它，运行其中唯一代码格即可执行下面这组验证，无需手动拼代码。Notebook会保存 `live_results.json`；正常保存Notebook会更新输出和元数据，因此Notebook本身不加入固定文件哈希门控。

在板上执行一整格：

```python
import json
import time
import pynq
from pynq import Overlay, Clocks
from board_check import verify_bundle, verify_overlay
from frontend import audio_init, stop_frontend
from pl_fft import FFTReceiver, InstrumentSession

print(verify_bundle('live'))
ol = Overlay('music_fft.bit')
print('PYNQ版本:', getattr(pynq, '__version__', 'unknown'))
print('加载后FCLK0 (MHz):', Clocks.fclk0_mhz)
if abs(float(Clocks.fclk0_mhz) - 50.0) > 0.1:
    Clocks.fclk0_mhz = 50.0
    time.sleep(0.05)
print('设置后FCLK0 (MHz):', Clocks.fclk0_mhz)
print(verify_overlay(ol))
rx = FFTReceiver(timeout=3.0)
try:
    print(audio_init())
    session = InstrumentSession(rx, model_dir='models', silence_rms=0.003)
    records = []
    for _ in range(10):
        result = session.next()
        records.append(result)
        print(json.dumps(result, ensure_ascii=False))
    with open('live_results.json', 'w') as f:
        json.dump(records, f, indent=2)
finally:
    stop_frontend()
    rx.close()
```

初始化打印当前 CPU_1x 推导的 IIC 输入频率和实际分频 SCL；不沿用硬编码100MHz。若自动时钟读取不可用，先读取实际运行平台的时钟，再显式传 `audio_init(i2c_input_hz=实际Hz)`。若 Linux 已占用 IIC0，程序在写寄存器前停止，需根据实际设备树使用内核 IIC 接口或调整占用；不要同时 MMIO 和 Linux 操作同一总线。

先检查加载后与设置后FCLK0输出（设置后应为50MHz），再检查 Codec 全部读回和 RX ctrl=1、tmr=12，随后给稳定单乐器音源。接收应持续、段号递增，关注 dropped/gap 与 compute_ms。rms_est 是 Hann 加权的功率估计；静音阈值0.003仅为初值，需按真实输入增益校准。非静音噪声仍可能被三分类模型强行归类。首次不加历史概率平滑，避免异常后沿用旧结果。

随后单独接外部500Hz已知音源，保存频谱并核对峰位、实际 LRCLK≈16kHz与幅度变化；内部 DDS 不能验证外部采样率或 ADC。按三类音源、静音、断流、60秒持续运行和冷启动逐项留存结果。当前双缓存允许显式丢整段，不承诺 gap 永远为0；若算力或调度造成持续丢段，再采用独立采集线程/队列并测量。

## 接口与验收范围

DMA0 0x40400000 保留旧峰值包；DMA1 0x40410000 是本协议，绝不是 PCM。每帧522个uint32=2088字节，TLAST在末word。14bit DMA长度够一帧，不能一次申请整段131544字节传输。

| word | 定义 |
|---|---|
| 0 | 新magic 0xA55A0402，拒绝混用旧0401接收程序 |
| 1 / 2 / 3 | 段号 / 帧号0..62 / 原始样本起点（uint32回卷） |
| 4 | 高16位累计丢段数低16bit；低16位错误标志，bit1为FFT帧错误 |
| 5 / 6 / 7 | 513 / 配置号1 / 保留0（不是RMS） |
| 8 | 本帧BFP exponent |
| 9..521 | bins0..512 的无符号实部²+虚部² |

已通过：16项 PC 接口/构建路径/端口返回回归、RTL/bench xvlog语法检查、Vivado2020.2 live综合实现及导出；AC820/PYNQ实测时钟修正、Codec读回、连续协议接收、真实线路响应与首次非静音推理执行。尚未通过/未运行：识别质量验收、RTL动态仿真、供应商FFT数值对拍、完整采样率/失真测量。此前xelab被本机MinGW DLL环境阻塞，不能宣称仿真通过。

构建回归包含真实Tcl文件操作和Vivado API stub，检查BD目录隔离、冻结输入定位及外置端口空返回情况；这部分测试本身不替代Vivado运行证据。本轮实际Vivado日志另行保留。

PC 接口测试：`python -m unittest discover -s integration/fft1024_pynq/tests -v`。

控制仿真（电脑命令行，测试目录）：

```text
xvlog ../rtl/music_pcm_segments.v ../rtl/music_fft1024_batch.v ../seed/sources_1/new/hann_coef_rom.v tb_fft_protocol.v tb_segments.v
xelab tb_fft_protocol -s protocol_test
xsim protocol_test -runall
xelab tb_segments -s segments_test
xsim segments_test -runall
```

第一个 bench 用 mock XFFT 检查输入逐点Q15/center、63帧、指数时序、反压及TLAST；它不能验证供应商FFT数值。第二个检查慢消费者缓存所有权、整段丢弃和恢复边界。bench 不加入硬件工程，避免 mock 覆盖真实 XFFT IP。
