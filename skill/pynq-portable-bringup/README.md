# 通用 PYNQ 部署与安全 DMA 接管

**适用范围**：使用 PYNQ Overlay、MMIO 和物理连续缓冲的开发；FPGA业务可以是采集、图像或其他流处理。离线HWH/清单检查不依赖PYNQ安装；DMA模板仅适用于寄存器兼容的 Xilinx AXI DMA simple S2MM 固定包接收。

**使用方法**：AI读取 SKILL.md；人工可按 references/workflow.md 执行。先跑 examples/offline_fixture，再填写自己工程的 spec.json。脚本只读文件；模板通过注入 mmio、allocate、producer_start/stop 适配实际驱动，不会自行选择板卡或下载bit。

```bash
python scripts/inspect_overlay.py --root examples/offline_fixture --spec examples/offline_fixture/spec.json
```

**来源**：集成中观察到硬件先被手动下载、又被正式入口重新下载，旧模块缓存和旧模型可能混用；主机停止故障测试表明必须在DMA停止未确认时保留内存。将“项目固定地址/数据格式”剥离为调用者契约，保留所有者与生命周期规则。

**已验证效果**：本技能测试以两种不同IP名称和地址的离线HWH检查替代项目写死映射；故障注入验证错哈希、错地址被拒绝，生产者在地址/长度提交后启动，停止失败时缓冲不释放，SG模式被拒绝。仅验证通用工具逻辑和mock行为，尚无陌生队伍或新板卡实测。

**失效条件**：HWH格式不同、映射命名不同、SG DMA/其他IP、变长帧、连续无停顿流、多所有者、缓存API不同、外部生产者不可停止等均需适配。模板不创建设备树、不初始化第三方音频/传感器、不推断DDR权限或时钟。哈希校验不能证明当前硬件配置与文件一致。

**通用性依据**：入口及模板无固定板卡、业务、地址、采样率或包长；更换overlay仅改spec和适配对象。此项可作为通用PYNQ Skill 提交，但加分认定由评审决定，不能把主机模拟称为跨板验证。

验证入口在完整技能包的 tests/run_skill_tests.py；单独使用本文件夹可先运行离线示例，硬件模板须先阅读工作流并在目标工程验证。示例payload.bin不是可上板bitstream。
