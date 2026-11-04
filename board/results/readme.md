# 上板运行记录

`current_r6/`收录最终R6软件的四轮完整LINE IN测试证据，包含原始采集ZIP、启动参数、控制台、音符与分类历史、测试条件及文件哈希。

`historical_*/`保留对应阶段的模型接口、连续分帧、音符事件及分类回放记录。各目录按照原测试阶段独立引用。

运行`python -B board/scripts/verify_board_evidence.py`可核对current_r6的所有原始归档成员、直接提取记录、对应输入音频及板端环境配对。
