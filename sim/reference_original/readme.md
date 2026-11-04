保留原始测试来源。原 test_system.py 还依赖旧 PC 界面，test_model_integration.py 依赖旧前端布局；不直接作为冻结包运行入口。可复现检查请用 sim/scripts/run_validation.py 与 run_rtl.py；报告会列明 mocked IP/主机/实物的边界。
