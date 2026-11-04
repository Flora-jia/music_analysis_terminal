# 板端环境与SD镜像

environment.json记录PYNQ、Python、NumPy、Pillow及内核版本。配套AC820 PYNQ 2.7.0镜像位于 `images/ac820_pynq_2_7_0.zip`，解压得到 `ACZ820_ZYNQ-2.7.0.img`，用于写入SD卡。镜像ZIP的SHA256见image_manifest.json，原始来源记录见image_receipt.json。使用镜像内既有Jupyter环境运行。

镜像体积约1.85GB，不在本仓库，请通过网盘获取（文件 AC820_ZYNQ_Pynq_Boot_img-2.7.0.zip，链接 https://pan.baidu.com/s/1XusxxofACUekKvr4DFvRVw?pwd=x2et 提取码 x2et），下载后按 image_manifest.json 核对SHA256，解压得到 ACZ820_ZYNQ-2.7.0.img。
