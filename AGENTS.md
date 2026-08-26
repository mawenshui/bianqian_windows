# StickyNote 项目维护与发布规范

本文件是本仓库的项目级工作规范，适用于人工开发、自动化代理和发布维护。用户在具体任务中的明确要求优先于本文件；若仓库实际情况与本文不一致，先核实并更新本文，不得靠猜测继续发版。

## 1. 当前项目基线

截至 2026-08-26，本地仓库状态如下：

- Git 分支：`main`，跟踪 `origin/main`；目录整理提交 `27a4ddc`、标签 `v1.7.8` 和 GitHub Release 均已同步。
- 当前代码版本：`1.7.8`。
- 版本来源：`core/__init__.py`、`features/__init__.py`、`setup.py`、`pyproject.toml`。
- 自动化测试：`tests/` 下有 17 个 `test_*.py` 文件；v1.7.8 整理后收集 306 项测试和 65 个子测试。
- 当前正式产物位于 `artifacts/releases/v1.7.8/`，并已发布至 GitHub Release；包含便携目录、Portable ZIP、MSI、发布说明和 SHA256 校验文件。
- 过时文档已移入 `docs/archive/` 并明确标记为历史资料；当前文档不得继续使用归档版本号描述现状。
- 发布工具已整理到 `tools/release/`；`create_release.py` 从目标版本目录读取资产和 UTF-8 发布说明，不再硬编码版本。
- Codex 工作区提供 Python 3.12 运行时，但项目测试及构建依赖仍需在使用前安装并验证。
- v1.7.8 发布时根据用户明确授权使用了系统环境变量 `GITHUB_TOKEN`；令牌未写入文件或发布日志。

以上内容是状态快照，不可替代每次任务开始时的重新检查。

## 2. 目录与文件职责

| 路径 | 用途 | 约束 |
| --- | --- | --- |
| `main.py` | 应用入口 | 只保留启动、单实例和顶层异常处理等入口逻辑 |
| `core/` | 核心模型、配置、日志、管理器和主要窗口 | 通用核心行为放在这里，不放临时脚本 |
| `features/` | 可独立维护的业务功能 | 新功能按模块拆分；同步相关代码放 `features/sync/`，插件框架放 `features/plugin_system/` |
| `plugins/` | 内置或示例插件 | 每个插件使用独立子目录 |
| `styles/` | 主题 CSS 与主题图标 | 主题说明维护在 `styles/readme.md` |
| `assets/` | 应用静态资源 | 图标统一放在 `assets/icons/`，不得散落到根目录 |
| `examples/` | 可提交的示例数据 | 文件名应明确带有 `example`，不得放入真实用户数据 |
| `tools/` | 可复用的开发、维护、卸载工具 | 新增工具需支持从仓库根目录运行并提供清晰的失败退出码 |
| `tests/` | 所有自动化测试 | 文件统一命名为 `test_*.py`；不得把正式测试脚本散落在根目录 |
| `docs/` | 开发、架构、需求、设计和发布流程文档 | 新增开发文档统一放这里，并更新 `docs/README.md` 索引 |
| `readme.md` | GitHub 首页和最终用户手册 | 保留在根目录；发布时同步版本号、下载文件名和用户可见变更 |
| `AGENTS.md` | 项目维护与交付规范 | 保留在根目录，流程变化时优先更新 |
| `runtime/` | 源码开发模式的全部用户数据 | 包含便签、备份、模板、日志及 JSON 配置，不提交 Git |
| `artifacts/build/`、`artifacts/dist/` | cx_Freeze 临时构建输出 | 可随时重建，不作为正式交付目录，不提交 Git |
| `artifacts/releases/vX.Y.Z/` | 单个版本的正式发布暂存目录 | 仅保留最终 MSI、Portable ZIP、发布说明和校验文件；目录不提交 Git |
| `artifacts/archive/portable-builds/` | 历史便携构建快照 | 仅本地保留，不提交 Git |
| `artifacts/test-results/` | UI 截图或其他测试证据 | 仅供本地诊断，不提交 Git |

旧版根目录文档已迁移到 `docs/archive/legacy-root/`。新增内容优先写入 `docs/` 中对应的权威文档；归档文档只保留历史上下文，不再作为当前规范维护。

## 3. 每次任务开始前

1. 执行 `git status --short --branch`，确认分支、上游和已有改动。
2. 现有未提交改动默认属于用户；不得覆盖、回滚或混入无关修改。
3. 用 `rg` 检索相关代码、测试、文档和版本引用，再决定修改范围。
4. 确认 Python、依赖和 Windows 构建工具可用。没有可用环境时，可以编辑文档或代码，但不得声称测试、构建或发布成功。
5. 开始发版前再次确认远端没有同名标签或 Release；已存在的版本不得覆盖，必须选择新版本号。

## 4. 代码修改与自动化测试

每次功能、修复或重构都必须完成以下闭环：

1. 实现最小且完整的变更，遵循 `docs/08-开发规范.md`。
2. 在 `tests/` 中新增或更新自动化测试，至少覆盖正常路径、相关边界条件和本次修复的回归场景。
3. 先运行受影响测试，再运行完整测试集。Windows PowerShell 推荐命令：

   ```powershell
   $env:QT_QPA_PLATFORM = 'offscreen'
   python -m compileall -q main.py core features plugins tests
   python -m pytest tests -v
   python -m pytest tests --cov=core --cov=features --cov-report=term-missing
   ```

4. 若完整覆盖率检查因既有环境或插件问题不可用，必须至少保证完整 `pytest` 通过，并在交付说明中记录原因；不得省略与本次修改直接相关的测试。
5. UI、快捷键、托盘、安装或升级相关变更除自动化测试外，还要做对应的 Windows 实机冒烟验证。
6. 测试失败时先修复代码或测试，全部通过后才能升级版本。不得通过删除测试、放宽关键断言或隐藏失败来推进发版。

测试结果需要在最终交付说明和 Release Notes 中写明测试数量、关键手工验证和任何未覆盖项。

## 5. 版本号规则

项目使用 `MAJOR.MINOR.PATCH`，例如 `1.2.3`：

- 小版本对应第 3 位 `PATCH`：兼容性修复、文档完善、小幅体验优化，例如 `1.2.3 -> 1.2.4`。
- 中版本对应第 2 位 `MINOR`：向后兼容的新功能或明显功能扩展，例如 `1.2.3 -> 1.3.0`。
- 大版本对应第 1 位 `MAJOR`：不兼容的数据、接口、安装或使用方式变更，例如 `1.2.3 -> 2.0.0`。

用户指定升级级别时严格按用户要求执行。用户未指定时，由维护者根据以上语义自行决定；默认规则是修复和小优化升 `PATCH`，新增兼容功能升 `MINOR`，只有明确破坏兼容性时才升 `MAJOR`。升级 `MINOR` 或 `MAJOR` 时，后续位归零。

只有纯分析、仅查看状态、尚未形成可交付修改的任务可以不升级版本。凡要打包和发布的代码变更必须使用高于最新 Git 标签和 GitHub Release 的新版本。

## 6. 版本与文档同步

版本确定后，至少检查并同步以下位置：

- `core/__init__.py` 中的 `__version__`。
- `features/__init__.py` 中的 `__version__`。
- `setup.py` 中的打包版本。
- `pyproject.toml` 中的项目版本。
- `StickyNote.egg-info/` 是可再生元数据，已停止跟踪并由 `.gitignore` 排除，不作为版本来源。
- `readme.md` 顶部版本、下载文件名、更新说明和文末适用版本。
- `docs/` 中所有受影响的架构、需求、设计、开发和计划文档。
- 根目录仍在使用的历史文档中的当前版本信息，或将其显式标为历史归档，避免出现多个“当前版本”。
- 测试中有意校验当前应用版本的断言；测试样例中的虚构版本号不需要机械替换。
- 本版本 `RELEASE_NOTES.md`。

完成后执行版本残留检查，确认旧版本只出现在历史日志或测试样例等合理位置：

```powershell
rg -n "旧版本号|当前版本|对应软件版本|文档版本" readme.md docs *.md core features tests setup.py pyproject.toml
```

所有 Markdown、Python、JSON、YAML 和发布说明统一使用 UTF-8。中文文档更新必须反映实际行为，不能只改版本号。

## 7. 构建、打包与产物验证

测试全部通过后再构建。正式发布必须同时生成双击安装版和便携版。

1. 清理或隔离本版本的临时输出，确保不会混入旧文件。
2. 使用 `setup.py` 和 cx_Freeze 生成冻结目录与 MSI：

   ```powershell
   python setup.py build_exe
   python setup.py bdist_msi
   ```

3. 若需修补 MSI 中文界面，必须显式传入本版本 MSI 路径：

   ```powershell
   python tools/release/patch_msi.py "artifacts\dist\StickyNote-X.Y.Z-win64.msi"
   ```

4. 创建唯一正式目录 `artifacts/releases/vX.Y.Z/`，将冻结目录复制为 `artifacts/releases/vX.Y.Z/StickyNote/`。
5. 将该 `StickyNote/` 目录压缩为 `StickyNote_vX.Y.Z_Portable.zip`，并将 MSI 统一命名为 `StickyNote-X.Y.Z-win64.msi`。
6. 在同一目录生成 UTF-8 的 `RELEASE_NOTES.md` 和包含两项正式资产 SHA256 的 `SHA256SUMS.txt`。

发布目录最终应为：

```text
artifacts/releases/vX.Y.Z/
├── StickyNote/                         # 便携版解压内容
├── StickyNote_vX.Y.Z_Portable.zip     # 便携版发布资产
├── StickyNote-X.Y.Z-win64.msi         # 双击安装版发布资产
├── RELEASE_NOTES.md                    # UTF-8 更新说明
└── SHA256SUMS.txt                      # 两个资产的 SHA256
```

构建后必须验证：

- 解压 Portable ZIP 后存在 `StickyNote.exe`、`styles/`、`plugins/` 和 `readme.md`。
- Portable `StickyNote.exe` 能启动并保持运行，退出后无致命日志。
- MSI 能通过 Windows Installer 管理解包或静默安装检查，且安装、桌面快捷方式、启动和卸载正常。
- 两个文件名和内嵌版本均为目标版本，不包含上一版本残留。
- 重新计算 SHA256，并与 `SHA256SUMS.txt` 一致。

任何一项失败都必须停止发布，修复后从测试开始重新验证。

## 8. Git 与 GitHub 发布

### 8.1 令牌和安全

- GitHub 写操作只能读取系统环境变量 `GTIHUB_TOKEN`。不得把令牌写入源码、配置、命令历史、Release Notes 或日志，也不得打印其值。
- 发布前只检查变量是否存在：

  ```powershell
  if ([string]::IsNullOrWhiteSpace($env:GTIHUB_TOKEN)) {
      throw '缺少系统环境变量 GTIHUB_TOKEN，停止发布。'
  }
  ```

- 使用 `python tools/release/create_release.py X.Y.Z` 创建 Release；脚本只读取 `GTIHUB_TOKEN`，不得因为系统里存在 `GITHUB_TOKEN` 就绕过本项目要求。

### 8.2 同步范围

- 源代码、测试和文档通过正常 Git 提交同步到 GitHub 仓库。
- `artifacts/` 中除 `README.md` 外的构建目录和安装文件不提交到 Git 历史；MSI、Portable ZIP、校验文件和发布说明上传到对应 GitHub Release。这就是“安装文件同步到 GitHub”的标准方式。
- 提交前检查 `git diff` 和 `git status`，确保没有用户数据、令牌、日志、缓存或无关构建目录。

### 8.3 顺序

正式发布按以下顺序执行，不得跳步：

1. 完成代码、测试和文档，确认工作区内容正确。
2. 执行完整自动化测试和必要的手工冒烟测试。
3. 升级并同步版本号，再重复完整测试。
4. 构建 MSI 与 Portable ZIP，完成产物验证和 SHA256 校验。
5. 提交代码、测试、文档和发布元数据，推送目标分支。
6. 创建带 `v` 前缀的 Git 标签 `vX.Y.Z`，推送标签。
7. 使用 `GTIHUB_TOKEN` 创建 GitHub Release，标题使用 `StickyNote vX.Y.Z`，正文读取本地 UTF-8 的 `RELEASE_NOTES.md`。
8. 上传 `StickyNote-X.Y.Z-win64.msi`、`StickyNote_vX.Y.Z_Portable.zip` 和 `SHA256SUMS.txt`。
9. 重新读取 GitHub Release，核对标签、正文、资产名称、资产数量和下载链接；必要时下载资产复核哈希。
10. 最后确认本地分支与远端同步、工作区无意外改动，再报告发布结果。

## 9. 中文 Release Notes 防乱码规范

- `RELEASE_NOTES.md` 必须以 UTF-8 保存；读取时显式指定 UTF-8。
- 调用 GitHub API 时，JSON 使用 UTF-8 编码，并设置 `Content-Type: application/json; charset=utf-8`；Python 序列化建议使用 `json.dumps(payload, ensure_ascii=False).encode('utf-8')`。
- 上传文件名包含中文时要做 URL 编码；本项目正式安装资产文件名保持 ASCII，可降低兼容风险。
- PowerShell 调用外部程序前可设置 `$env:PYTHONUTF8 = '1'`；不得用系统默认 ANSI 编码生成或管道传递中文发布说明。
- 发布后必须从 GitHub API 或页面重新读取正文，确认中文显示正确。仅接口返回成功不代表编码验证通过。

## 10. 完成定义

一个需要发布的修改只有同时满足以下条件才算完成：

- 代码实现完成，相关自动化测试已补齐。
- 受影响测试、完整测试、覆盖率或替代验证全部有明确结果。
- 版本号按语义升级且所有版本来源一致。
- 用户文档、开发文档、历史兼容文档和 Release Notes 已更新到实际状态。
- MSI 与 Portable ZIP 均已生成并通过验证，SHA256 已记录。
- 代码、测试和文档已推送 GitHub；标签和 Release 已创建。
- Release 中的 MSI、Portable ZIP 和校验文件均可见，中文更新说明无乱码。
- 最终报告列出版本号、测试结果、产物路径、SHA256、提交、标签和 Release 链接；未完成项必须明确说明，不能写成已完成。
