# 构建与发布产物目录

本目录统一存放本地生成物，除本说明外均不提交 Git。

- `build/`：cx_Freeze 冻结目录和构建临时文件。
- `dist/`：MSI 等待整理的打包输出。
- `releases/vX.Y.Z/`：正式版本的 MSI、Portable ZIP、发布说明和 SHA256。
- `archive/portable-builds/`：历史便携构建快照，仅供本地比对。
- `test-results/`：UI 截图和其他测试证据。

正式资产命名及发布流程见根目录 `AGENTS.md`。
