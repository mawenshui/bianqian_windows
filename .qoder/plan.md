# StickyNote v1.6.3 优化实现计划

## Context

本项目是 PyQt5 桌面便签应用，当前版本 v1.6.2。根据 `docs/09-优化计划.md` 文档，需要按顺序完成以下优化任务，最终升级至 v1.6.3 并进行完整自动化测试。

## 任务分解

### 任务 1: 3.6 错误处理规范化
**目标**：统一 4 种不一致的错误处理模式（静默吞掉/只打日志/弹窗提示/重新抛出）

**涉及文件**：
- 新建 `core/errors.py` — 统一异常层次结构（StickyNoteError 基类 + DataError/FileOperationError/PluginError/SearchError 子类）和 `handle_error()` 统一入口
- 修改 `core/note.py` — 将 ~10 处 `except Exception: pass` 改为至少记录 debug/warning 日志
- 修改 `core/manager.py` — 将 ~5 处静默吞掉改为日志记录
- 修改 `features/search.py` — 统一使用 SearchError
- 修改 `main.py` — 精确异常捕获

**策略**：UI层弹窗（QMessageBox）→ 业务层日志（logger）→ 底层 raise → 插件层禁止崩溃

---

### 任务 2: 4.7 搜索功能增强
**目标**：结果相关度排序、标签过滤、Ctrl+F 便签内搜索、内容预览加长至100字符

**涉及文件**：
- 修改 `features/search.py` — 添加 `_compute_relevance()` 方法实现标题优先排序；添加 `QComboBox` 标签过滤器；修改 `perform_search()` 按分数排序和标签过滤；内容预览从50→100字符
- 修改 `core/note.py` — 添加 `_show_inline_search()` 方法：在编辑器上方显示搜索条，支持 `QTextEdit.find()` 高亮和上/下一个导航，Esc关闭
- 修改 `features/shortcuts.py` — 注册 Ctrl+F 快捷键绑定到当前便签的内联搜索

---

### 任务 3: 4.9 便签批量操作与置顶
**目标**：批量删除/打标签/导出，置顶/收藏，托盘自定义排序

**涉及文件**：
- 修改 `core/manager.py` — 添加 `batch_delete_notes()`、`batch_tag_notes()`、`batch_export_notes()` 批量方法；添加 `toggle_note_pin()`、`toggle_note_favorite()` 方法；修改 `update_tray_menu()` 排序：置顶→收藏→普通
- 修改 `core/note.py` — note_data 增加 `pinned`/`favorite` 字段；右键菜单添加"置顶/收藏"选项；置顶时更新窗口标志
- 修改 `features/group_view.py` — GroupViewDialog 添加多选（Ctrl/Shift+点击），工具栏添加 `[批量删除] [批量打标签] [批量导出]` 按钮

---

### 任务 4: 5.5 撤销/重做视觉反馈
**目标**：工具栏显示撤销/重做按钮状态和栈深度

**涉及文件**：
- 修改 `features/undo_redo.py` — `state_changed` 信号增加 `(can_undo, can_redo)` 参数；添加 `get_stack_depth()` 返回 `(undo_count, redo_count)`
- 修改 `core/note.py` — 工具栏撤销/重做按钮连接 `state_changed` 信号，动态更新 `setEnabled()` 和 tooltip（如"撤销 (Ctrl+Z) [5次可用]"）

---

### 任务 5: 5.6 主题热加载
**目标**：监听 styles 目录变化，自动刷新已打开便签主题

**涉及文件**：
- 修改 `features/theme_helper.py` — 添加 `start_theme_watcher()` 使用 `QFileSystemWatcher` 监听 styles 目录及所有 .css 文件；添加 `stop_theme_watcher()`；添加 `invalidate_cache()` 清除主题缓存；目录变化时加 500ms 防抖
- 修改 `core/manager.py` — `__init__` 末尾调用 `start_theme_watcher()`，添加 `_on_theme_files_changed()` 回调：清除缓存 + 刷新所有便签主题

---

### 任务 6: 6.5 JSON 深拷贝优化
**目标**：用 `copy.deepcopy()` 替换 `json.loads(json.dumps())`

**涉及文件**：
- 修改 `core/note.py` L1372 — `json.loads(json.dumps(self.note_data))` → `copy.deepcopy(self.note_data)`

---

### 任务 7: 6.6 paintEvent 渲染缓存
**目标**：缓存 QPen 对象，避免每次 paintEvent 重复创建

**涉及文件**：
- 修改 `core/note.py` `__init__` — 添加 `self._border_pen = QPen(QColor(200, 200, 200), 2)` 实例属性
- 修改 `core/note.py` `paintEvent` — 直接使用 `self._border_pen`
- 修改 `core/note.py` `set_theme` — 主题切换时更新 `_border_pen` 颜色

---

### 任务 8: 6.7 屏幕几何信息缓存
**目标**：缓存 `availableGeometry` 结果，1秒有效期

**涉及文件**：
- 修改 `core/note.py` `__init__` — 添加 `_cached_screen_geo` 和 `_screen_geo_cache_time` 缓存
- 修改 `core/note.py` — 新增 `_get_screen_geometry()` 方法，1秒内返回缓存值
- 修改 `core/note.py` — 替换 ~8 处 `QApplication.desktop().availableGeometry(self)` 调用为 `self._get_screen_geometry()`

---

### 任务 9: 6.8 搜索目录列表缓存
**目标**：构建内存索引，避免每次搜索都 `os.listdir()` + 逐文件读取

**涉及文件**：
- 修改 `features/search.py` — 添加模块级 `_note_index` 字典和 `_build_or_refresh_index()` 方法；`perform_search()` 中使用索引替代 `os.listdir()` 遍历；索引通过 `_index_dirty` 标记增量更新

---

### 任务 10: 7.6 路径穿越防护
**目标**：对便签文件路径进行规范化验证，确保在 notes_dir 内

**涉及文件**：
- 修改 `core/note.py` `__init__` — `note_file` 创建后使用 `os.path.realpath()` 验证路径
- 修改 `core/manager.py` `load_notes` — 加载文件时验证路径不穿越

---

### 任务 11: 9.1 依赖管理完善
**目标**：创建 pyproject.toml 和 requirements.txt，区分核心/可选依赖

**涉及文件**：
- 新建 `pyproject.toml` — 包含 [build-system]、[project]、[project.optional-dependencies]（crypto/markdown/sync/all）
- 新建 `requirements.txt` — 开发依赖列表
- 修改 `setup.py` — 版本号改为 1.6.3

---

### 任务 12: 9.2 配置版本迁移机制
**目标**：添加 `config_version` 字段和迁移函数链

**涉及文件**：
- 修改 `core/config.py` — `DEFAULT_SETTINGS` 添加 `config_version: 1`；新增 `_migration_chain` 列表和 `_register_migration()` 装饰器；修改 `load()` 方法在合并默认值后按序执行迁移链；添加示例迁移函数 `_migrate_0_to_1`

---

### 任务 13: 3.3 单元测试覆盖
**目标**：为关键模块补充测试

**涉及文件**（新建）：
- `tests/test_note.py` — TestStickyNoteCreation, TestStickyNoteSaveLoad, TestStickyNoteDataIntegrity, TestStickyNoteGeometry
- `tests/test_search.py` — TestSearchRelevance, TestSearchTagFilter
- `tests/test_tag.py` — TestTagManager, TestBatchTag
- `tests/test_undo_redo.py` — TestUndoRedoManager, TestUndoRedoStackDepth
- `tests/test_errors.py` — TestErrorHierarchy, TestHandleError

---

### 任务 14: 版本升级、全量测试、文档更新
**涉及文件**：
- `core/__init__.py` — 版本号 1.6.2 → 1.6.3
- `setup.py` — 版本号 1.6.2 → 1.6.3
- `pyproject.toml` — 版本号 1.6.3
- `docs/09-优化计划.md` — 更新已完成状态
- `readme.md` — 更新版本号

---

## 执行顺序

按用户指定顺序执行：
1. 任务1（错误处理）→ 2（搜索增强）→ 3（批量操作）
2. 任务4（撤销反馈）→ 5（主题热加载）
3. 任务6（JSON深拷贝）→ 7（paintEvent）→ 8（屏幕几何）→ 9（搜索索引）
4. 任务10（路径安全）
5. 任务11（依赖管理）→ 12（配置迁移）
6. 任务13（单元测试）
7. 任务14（版本升级 + 全量测试 + 文档更新）

## 验证方案

1. 每个任务完成后运行相关测试：`python -m pytest tests/ -v`
2. 全量回归测试：`python -m pytest tests/ -v --cov=core --cov=features`
3. 手动启动验证：`python main.py` 确认应用正常启动和核心功能
