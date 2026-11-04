# 构建和交付脚本

rebuild.py调用rebuild.tcl重建Vivado工程，build_native.py编译C库。create_submission_manifest.py生成交付清单，verify_release.py校验文件，package_submission.py支持ZIP和RAR5归档，package_release.py提供ZIP归档。已有清单可用--out指定新的收据路径。
