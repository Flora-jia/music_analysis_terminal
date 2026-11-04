# R6真实上板记录

四轮采集按case分别保存，capture为原始采集内容，original_capture.zip为完整原始文件，analysis.json保存统计。wired_model_nofeatures01对应input=line、模型开启、诊断特征录制关闭，piano-review关闭。其余case记录对应的模型、录制和界面操作条件。

参考输入为data/audio/acceptance中的三组音频，电脑音量100%。smoke02现场操作了触摸及节拍器，播放顺序为纯音、音阶、同音；nomodel01为纯音、同音、音阶。运行参数以各case中的run_arguments和控制台为准。
