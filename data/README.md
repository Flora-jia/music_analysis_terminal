# 测试输入与参考结果

audio、labels与generators保存54条固定回归音频、84条参考标注及生成脚本。优先播放audio/acceptance的纯音、六音阶和三次同音，并参照labels/acceptance/expected.csv。

classification_r6保存221条乐器音频、185条字节唯一输入、逐文件与2154条逐秒结果。其README注明分段、静音和文件级投票统计方法，输入内容哈希及提供方标签位于data/input_manifest.json和data/labels/expected.csv。

音频来源和原始标识见provenance.md及各组清单。平台复现目录以classification_archive.zip保存相同分类测试包。
