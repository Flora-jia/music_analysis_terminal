# 板端环境与SD镜像

environment.json记录PYNQ、Python、NumPy、Pillow及内核版本。配套AC820 PYNQ 2.7.0镜像位于 `images/ac820_pynq_2_7_0.zip`，解压得到 `ACZ820_ZYNQ-2.7.0.img`，用于写入SD卡。镜像ZIP的SHA256见image_manifest.json，原始来源记录见image_receipt.json。使用镜像内既有Jupyter环境运行。

镜像通过Git LFS管理，克隆后执行 `git lfs pull` 下载实际ZIP文件，再校验SHA256。
