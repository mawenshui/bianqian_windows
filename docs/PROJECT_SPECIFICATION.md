# StickyNote 项目规范文档

## 项目概述

**StickyNote** 是一款基于 PyQt5 开发的 Windows 桌面便签应用程序，提供便签创建、编辑、管理和主题自定义等功能。本项目采用面向对象设计，支持多便签管理、系统托盘集成、开机自启动等特性。

### 项目信息
- **项目名称**: StickyNote
- **开发语言**: Python 3.x
- **GUI框架**: PyQt5
- **目标平台**: Windows 10+
- **开发者**: MaWenshui
- **当前版本**: 1.5.3
- **最后更新**: 2026年6月
- **主要特性**: 富文本编辑、多主题支持、智能定位、数据备份、定时提醒、标签管理、导入导出、模板系统、右键菜单、窗口吸附、动画效果、异步I/O

---

## 项目架构

### 目录结构
```
bianqian_windows/
├── main.py                 # 主程序入口文件
├── settings.json           # 应用配置文件
├── tags.json               # 标签数据文件 (v1.2.0)
├── window_positions.json   # 窗口位置记录文件
├── readme.md              # 用户使用手册
├── PROJECT_SPECIFICATION.md # 项目规范文档（本文件）
├── IMPROVEMENT_PLAN.md    # 项目改进计划文档
├── core/                  # 核心模块目录 (v1.3.0 拆分)
│   ├── __init__.py        # 模块导出，版本号
│   ├── note.py            # 便签窗口组件 + 异步I/O Worker
│   ├── manager.py         # 应用管理器 (StickyNoteManager)
│   └── settings.py        # 设置对话框 (SettingsDialog)
├── features/              # 功能模块目录 (v1.1.0新增)
│   ├── __init__.py
│   ├── search.py          # 搜索功能模块
│   ├── backup.py          # 数据备份模块
│   ├── shortcuts.py       # 全局快捷键模块
│   ├── positioning.py     # 智能窗口定位模块
│   ├── undo_redo.py       # 撤销/重做功能模块
│   ├── formatter.py       # 智能格式化模块 (v1.2.0)
│   ├── reminder.py        # 定时提醒模块 (v1.2.0)
│   ├── tag.py             # 标签管理模块 (v1.2.0)
│   ├── import_export.py   # 导入导出模块 (v1.2.0)
│   └── template.py        # 便签模板模块 (v1.2.0)
├── notes/                 # 便签数据存储目录（运行时创建）
│   ├── note_1.json       # 便签数据文件
│   ├── note_2.json
│   └── ...
├── backups/               # 备份文件存储目录 (v1.1.0)
│   ├── backup_settings.json
│   └── ...
├── templates/             # 自定义模板存储 (v1.2.0)
│   └── ...
└── styles/                # 主题样式文件目录
    ├── classic_white.css
    ├── elegant_green.css
    ├── fresh_blue.css
    ├── midnight_black.css
    ├── ocean_teal.css
    ├── soft_yellow.css
    ├── sunny_orange.css
    ├── sunset_orange.css
    ├── vibrant_purple.css
    ├── warm_pink.css
    ├── readme.md         # 主题开发指南
    └── readme.pdf
```

### 核心模块架构

#### 1. 核心模块 (core/) - v1.3.0 从 main.py 拆分
- **StickyNoteManager** (manager.py): 应用管理器，中央控制器
- **StickyNote** (note.py): 便签窗口组件，含右键菜单/吸附/动画
- **PlainLineEdit** (note.py): 纯文本标题编辑器
- **PlainTextEdit** (note.py): 纯文本内容编辑器
- **NoteSaveWorker** (note.py): 异步保存后台线程
- **NoteLoadWorker** (note.py): 异步加载后台线程
- **SettingsDialog** (settings.py): 主题+字体设置对话框

#### 2. 功能模块 (features/) - v1.1.0 扩展至 v1.2.0
- **SearchManager / SearchDialog**: 便签搜索功能 (search.py)
- **ShortcutManager**: 全局快捷键管理 (shortcuts.py)
- **BackupManager / BackupDialog**: 数据备份管理 (backup.py)
- **WindowPositionManager**: 智能窗口定位 (positioning.py)
- **UndoRedoManager / UndoRedoTextEdit / UndoRedoLineEdit**: 撤销重做 (undo_redo.py)
- **ContentFormatter**: 智能格式化粘贴 (formatter.py) — v1.2.0
- **ReminderManager / ReminderDialog / ReminderData**: 定时提醒 (reminder.py) — v1.2.0
- **TagManager / TagEditDialog / NoteTagSelector**: 标签管理 (tag.py) — v1.2.0
- **ImportExportDialog / ExportWorker**: 导入导出 (import_export.py) — v1.2.0
- **TemplateManager / TemplateDialog**: 模板系统 (template.py) — v1.2.0

#### 3. 数据存储模块
- **便签数据**: JSON格式存储在 `notes/` 目录
- **应用设置**: JSON格式存储在 `settings.json`
- **标签数据**: JSON格式存储在 `tags.json` — v1.2.0
- **窗口位置**: JSON格式存储在 `window_positions.json`
- **备份数据**: 存储在 `backups/` 目录
- **自定义模板**: JSON格式存储在 `templates/` 目录 — v1.2.0

#### 4. 主题系统模块
- **CSS样式文件**: 存储在 `styles/` 目录（10种主题）
- **主题管理**: 动态加载和应用主题，支持暗色/亮色自适应控件样式

---

## 核心功能模块

### 1. 便签管理模块

#### 功能特性
- 创建新便签
- 编辑便签标题和内容
- 删除便签
- 隐藏/显示便签
- 便签窗口拖拽和调整大小
- 便签透明度调节
- 字体大小调节（A+/A-按钮）
- 文本格式设置（加粗、斜体、字体颜色）- Version 1.2.0新增
- 智能格式化（JSON、HTML、Markdown等）
- 总在最前设置

#### 数据结构
```json
{
    "title": "便签标题",
    "content": "<p><b>富文本内容</b> <i>斜体文本</i> <span style='color: #ff0000;'>彩色文本</span></p>",
    "plain_content": "富文本内容 斜体文本 彩色文本",
    "opacity": 0.9,
    "always_on_top": true,
    "geometry": {
        "x": 100,
        "y": 100,
        "width": 400,
        "height": 300
    },
    "theme": "soft_yellow.css",
    "title_font_size": 12,
    "content_font_size": 12,
    "font_settings": {
        "family": "微软雅黑",
        "size": 12,
        "bold": false,
        "italic": false
    },
    "font_color": "#000000",
    "auto_format_enabled": true,
    "tags": ["工作", "重要"],
    "reminder": {
        "enabled": true,
        "datetime": "2025-06-05T09:00",
        "repeat": "daily",
        "message": "提醒消息",
        "last_triggered": "2025-06-04"
    },
    "template": "todo"
}
```

#### 字段说明
- **content**: 便签主要内容，v1.2.0起支持HTML格式存储
- **plain_content**: 纯文本内容备份，用于搜索和向下兼容
- **font_color**: 字体颜色设置，十六进制颜色代码
- **font_settings**: 字体相关设置，包括字体族、大小、加粗、斜体状态
- **auto_format_enabled**: 自动格式化开关状态
- **tags**: 标签列表 (v1.2.0 新增)
- **reminder**: 提醒设置 (v1.2.0 新增)，包含 enabled/datetime/repeat/message/last_triggered
- **template**: 创建时使用的模板标识 (v1.2.0 新增)

### 2. 系统托盘模块

#### 功能特性
- 托盘图标显示
- 右键菜单管理
- 便签列表显示
- 快速操作入口
- 双击打开便签

#### 菜单结构
- 添加便签 (Ctrl+Shift+N)
- 从模板创建...
- 搜索便签 (Ctrl+Shift+F)
- 备份管理 (Ctrl+Shift+B)
- 导入导出
- ─────────
- 便签列表（子菜单）
  - 便签标题 → 打开 / 删除
- 标签分组（子菜单）
  - 标签名 → 该标签下的便签列表
- 管理标签
- ─────────
- 开机自启
- 设置
- 退出

### 3. 主题系统模块

#### 功能特性
- 多主题支持
- 动态主题切换
- 主题名称自动识别
- 全局主题应用

#### 主题文件规范
```css
/* Theme Name: 主题名称 */

StickyNote {
    background-color: #颜色代码;
    color: #文字颜色;
}

/* 其他控件样式定义 */
```

### 4. 搜索功能模块 - Version 1.1.0新增

#### 功能特性
- 按标题搜索便签
- 按内容搜索便签
- 实时搜索结果显示
- 搜索结果快速打开
- 现代化搜索界面

#### 核心类
- **SearchManager**: 搜索功能管理器
- **SearchDialog**: 搜索对话框界面

#### 快捷键
- **Ctrl+Shift+F**: 打开搜索对话框

### 5. 撤销/重做功能模块 - Version 1.1.0新增

#### 功能特性
- 标题编辑撤销/重做
- 内容编辑撤销/重做
- 多级撤销支持
- 标准快捷键支持

#### 核心类
- **UndoRedoLineEdit**: 支持撤销/重做的单行编辑器
- **UndoRedoTextEdit**: 支持撤销/重做的文本编辑器

#### 快捷键
- **Ctrl+Z**: 撤销操作
- **Ctrl+Y**: 重做操作

### 6. 全局快捷键模块 - Version 1.1.0新增

#### 功能特性
- 全局快捷键注册
- 系统级快捷键监听
- 快捷键冲突检测
- 动态快捷键管理

#### 核心类
- **ShortcutManager**: 快捷键管理器
- **GlobalShortcutManager**: 全局快捷键管理器
- **LocalShortcutManager**: 本地快捷键管理器

#### 支持的快捷键
- **Ctrl+Shift+N**: 创建新便签
- **Ctrl+Shift+F**: 打开搜索对话框
- **Ctrl+Shift+B**: 打开备份管理对话框

### 7. 智能窗口定位模块 - Version 1.1.0新增

#### 功能特性
- 智能窗口位置计算
- 避免窗口重叠
- 多显示器支持
- 窗口位置记忆
- 屏幕边界检测

#### 核心类
- **WindowPositionManager**: 窗口位置管理器

#### 数据存储
- **window_positions.json**: 窗口位置记录文件

### 8. 数据备份模块 - Version 1.1.0新增

#### 功能特性
- 自动备份便签数据
- 手动备份创建
- 备份文件管理
- 数据恢复功能
- 备份文件清理

#### 核心类
- **BackupManager**: 备份管理器
- **BackupDialog**: 备份管理对话框

#### 备份策略
- 自动备份频率可配置
- 备份文件命名规范
- 备份文件压缩存储

#### 快捷键
- **Ctrl+Shift+B**: 打开备份管理对话框

### 9. 定时提醒模块 - Version 1.2.0新增

#### 功能特性
- 一次性提醒（指定日期时间）
- 周期提醒（每天/每周/每月）
- 到期时系统托盘通知（5秒弹出）
- 提醒数据持久化到便签 JSON 中
- 防重复触发（last_triggered 日期跟踪）
- 提醒按钮状态可视化

#### 核心类
- **ReminderManager**: 提醒管理器，每30秒轮询检查
- **ReminderDialog**: 提醒设置对话框
- **ReminderData**: 提醒数据模型（含 is_due/mark_triggered）
- **RepeatMode**: 重复模式枚举 (once/daily/weekly/monthly)

### 10. 标签管理模块 - Version 1.2.0新增

#### 功能特性
- 标签 CRUD（创建、重命名、删除）
- 标签颜色自定义（12种预设色 + 颜色选择器）
- 便签多标签关联
- 托盘菜单按标签分组显示
- 标签芯片组件（便签上显示，点击×移除）
- 标签数据持久化到 tags.json

#### 核心类
- **TagManager**: 标签管理器
- **TagEditDialog**: 标签编辑对话框
- **NoteTagSelector**: 便签标签选择器
- **TagChipWidget**: 标签芯片组件

#### 预设颜色
12种预设标签颜色: #e74c3c, #e67e22, #f1c40f, #2ecc71, #3498db, #9b59b6, #1abc9c, #34495e, #e91e63, #00bcd4, #ff5722, #607d8b

### 11. 导入导出模块 - Version 1.2.0新增

#### 功能特性
- 单便签导出为 TXT / Markdown
- 批量导出所有便签为 ZIP 压缩包
- 从 TXT 文件导入创建便签
- 多文件批量导入
- 后台线程异步导出（不阻塞UI）
- 导出进度条显示

#### 核心类
- **ImportExportDialog**: 导入导出对话框
- **ExportWorker**: 导出工作线程 (QThread)

### 12. 模板系统模块 - Version 1.2.0新增

#### 功能特性
- 5个内置模板：待办清单、会议纪要、周计划、每日日志、头脑风暴
- 用户自定义模板（保存到 templates/ 目录）
- 模板预览和编辑
- {date} 占位符自动替换为当前日期
- 从模板快速创建便签
- 内置模板不可删除

#### 核心类
- **TemplateManager**: 模板管理器
- **TemplateDialog**: 模板选择和编辑对话框

#### 内置模板
| 标识 | 名称 | 图标 |
|------|------|------|
| todo | 待办清单 | ✅ |
| meeting | 会议纪要 | 📋 |
| weekplan | 周计划 | 📅 |
| daily | 每日日志 | 📝 |
| brainstorm | 头脑风暴 | 💡 |

### 13. 智能格式化模块 - Version 1.2.0新增

#### 功能特性
- 粘贴时自动识别内容类型
- 支持 8 种格式：JSON、HTML、Markdown、XML、CSS、JavaScript、Python、SQL
- 可开关的自动格式化（每个便签独立设置）
- JSON 自动美化格式化

#### 核心类
- **ContentFormatter**: 内容格式化器
- **SmartTextEdit**: 智能文本编辑器（备用）

### 14. 右键上下文菜单 - Version 1.3.0新增

#### 功能特性
- 复制全部内容 / 粘贴
- 切换主题（子菜单，当前主题已勾选）
- 字体设置（增大/减小字体）
- 总在最前开关
- 透明度选择（QActionGroup 互斥，8档: 30%~100%）
- 设置标签 / 设置提醒
- 隐藏便签 / 删除便签

#### 实现
- `StickyNote.contextMenuEvent()` 方法 (约100行)

### 15. 窗口吸附 - Version 1.3.0新增

#### 功能特性
- 屏幕边缘吸附（上下左右四边，阈值15px）
- 便签间边缘对齐（左贴右、右贴左、上贴下、下贴上、边缘对齐）
- 拖拽释放时自动触发

#### 实现
- `StickyNote._apply_snapping()` / `StickyNote._snap_to_window()` 方法
- 常量 `SNAP_THRESHOLD = 15`

### 16. 淡入淡出动画 - Version 1.3.0新增

#### 功能特性
- 窗口显示时 200ms 淡入 (OutCubic 缓动)
- 窗口隐藏时 150ms 淡出 (InCubic 缓动)
- 隐藏后恢复原始透明度

#### 实现
- `StickyNote.showEvent()` 重写
- `StickyNote._fade_out_and_hide()` / `StickyNote._on_fade_out_finished()` 方法
- 使用 `QPropertyAnimation(windowOpacity)`

### 17. 异步 I/O - Version 1.3.0新增

#### 功能特性
- 保存异步化：NoteSaveWorker 后台线程 + 500ms 防抖
- 加载异步化：NoteLoadWorker 后台线程 + preloaded_data 参数跳过重复读取
- 加载进度追踪：_pending_loaders / _loaded_note_count

#### 核心类
- **NoteSaveWorker** (note.py): 异步保存工作线程
- **NoteLoadWorker** (note.py): 异步加载工作线程
  - `loaded(note_id, data)` 信号
  - `failed(note_id, error)` 信号

### 18. 设置管理模块

#### 功能特性
- 默认主题设置
- 开机自启动设置
- 设置持久化存储

#### 配置文件结构
```json
{
    "default_theme": "elegant_green.css",
    "default_font_size": 6
}
```

### 10. 文本格式功能模块 - Version 1.2.0新增

#### 功能特性
- **加粗格式**: 支持文本加粗显示
- **斜体格式**: 支持文本斜体显示
- **字体颜色**: 支持自定义字体颜色选择
- **选择性应用**: 可对选中文本或光标位置应用格式
- **格式状态显示**: 工具栏按钮显示当前格式状态
- **格式持久化**: 格式设置随便签数据自动保存
- **富文本存储**: 便签内容以HTML格式保存，保留所有格式信息
- **向下兼容**: 支持加载旧版本纯文本便签

#### 核心功能
- **toggle_bold()**: 切换加粗状态，支持选中文本和光标位置
- **toggle_italic()**: 切换斜体状态，支持选中文本和光标位置
- **choose_font_color()**: 打开颜色选择器，设置字体颜色
- **apply_font()**: 应用字体设置到编辑器
- **apply_rich_text_format()**: 应用富文本格式到编辑器
- **save_note()**: 保存富文本内容为HTML格式

#### 工具栏按钮
- **B按钮**: 加粗格式切换，选中时显示蓝色背景(#007ACC)
- **I按钮**: 斜体格式切换，选中时显示蓝色背景(#007ACC)
- **A按钮**: 字体颜色选择，按钮背景色显示当前选择的颜色

#### 技术实现
- **富文本格式**: 使用 `QTextCharFormat` 实现富文本格式控制
- **HTML存储**: 便签内容以HTML格式存储，保留完整格式信息
- **纯文本备份**: 同时保存纯文本版本作为备用和搜索索引
- **格式同步**: 按钮状态与文本格式实时同步显示
- **主题兼容**: 格式设置与主题系统完全兼容
- **选择检测**: 智能检测文本选择状态，精确应用格式

#### 数据结构扩展
```json
{
    "content": "<p><b>加粗文本</b> <i>斜体文本</i> <span style='color: #ff0000;'>红色文本</span></p>",
    "plain_content": "加粗文本 斜体文本 红色文本",
    "font_color": "#000000",
    "font_settings": {
        "family": "微软雅黑",
        "size": 12,
        "bold": false,
        "italic": false
    }
}
```

---

## 代码规范

### 1. 命名规范

#### 类命名
- 使用 PascalCase（帕斯卡命名法）
- 示例: `StickyNote`, `StickyNoteManager`, `SettingsDialog`

#### 方法命名
- 使用 snake_case（下划线命名法）
- 示例: `load_note()`, `save_note()`, `update_title()`

#### 变量命名
- 使用 snake_case（下划线命名法）
- 示例: `note_id`, `notes_dir`, `theme_css`

#### 常量命名
- 使用 UPPER_CASE（全大写下划线）
- 示例: `RESIZE_MARGIN = 10`

### 2. 注释规范

#### 函数注释
```python
def function_name(param1, param2):
    """
    函数功能描述
    
    Args:
        param1 (type): 参数1描述
        param2 (type): 参数2描述
    
    Returns:
        type: 返回值描述
    """
    pass
```

#### 类注释
```python
class ClassName:
    """
    类功能描述
    
    Attributes:
        attribute1 (type): 属性1描述
        attribute2 (type): 属性2描述
    """
    pass
```

#### 行内注释
- 使用 `#` 进行行内注释
- 注释应简洁明了，解释代码意图

### 3. 代码结构规范

#### 导入顺序
1. 标准库导入
2. 第三方库导入
3. 本地模块导入

#### 类结构顺序
1. 类文档字符串
2. 类变量
3. `__init__` 方法
4. 公共方法
5. 私有方法
6. 特殊方法（如 `__str__`, `__repr__`）

---

## 开发指南

### 1. 环境配置

#### 系统要求
- Windows 10 或更高版本
- Python 3.7+
- PyQt5 5.15+

#### 依赖安装
```bash
pip install PyQt5
```

#### 开发工具推荐
- IDE: PyCharm, VS Code
- 版本控制: Git
- 代码格式化: Black, autopep8

### 2. 运行和调试

#### 启动应用
```bash
python main.py
```

#### 调试模式
- 在代码中添加 `print()` 语句进行调试
- 使用 IDE 的调试功能设置断点

### 3. 新功能开发流程

#### 1. 需求分析
- 明确功能需求
- 设计用户界面
- 确定数据结构

#### 2. 代码实现
- 遵循现有代码规范
- 添加必要的注释
- 实现错误处理

#### 3. 测试验证
- 功能测试
- 边界条件测试
- 用户体验测试

#### 4. 文档更新
- 更新用户手册
- 更新项目规范
- 添加代码注释

---

## 主题开发规范

### 1. 主题文件命名
- 使用小写字母和下划线
- 格式: `theme_name.css`
- 示例: `soft_yellow.css`, `elegant_green.css`

### 2. 主题文件结构
```css
/* Theme Name: 主题显示名称 */

/* 主窗口样式 */
StickyNote {
    background-color: #背景色;
    color: #文字色;
}

/* 标题输入框样式 */
QLineEdit {
    background-color: #背景色;
    border: 2px solid #边框色;
    border-radius: 5px;
    font-family: "微软雅黑";
    font-weight: bold;
    text-align: center;
    padding: 5px;
    color: #文字色;
}

/* 内容编辑区样式 */
QTextEdit {
    background-color: #背景色;
    border: 2px solid #边框色;
    border-radius: 5px;
    padding: 5px;
    font-family: "微软雅黑";
    color: #文字色;
}

/* 按钮样式 */
QPushButton {
    background-color: #按钮背景色;
    color: #按钮文字色;
    border: none;
    border-radius: 5px;
    font-family: "微软雅黑";
    padding: 5px;
}

QPushButton:hover {
    background-color: #悬停背景色;
}

/* 滑块样式 */
QSlider::handle:horizontal {
    background-color: #滑块颜色;
    border: 1px solid #边框色;
    width: 18px;
    margin: -2px 0;
    border-radius: 3px;
}

/* 复选框样式 */
QCheckBox {
    color: #文字色;
    font-family: "微软雅黑";
}

QCheckBox::indicator:checked {
    background-color: #选中背景色;
    border: 1px solid #边框色;
}

/* 设置对话框样式 */
QDialog {
    background-color: #对话框背景色;
    color: #文字色;
}

/* 下拉框样式 */
QComboBox {
    background-color: #背景色;
    border: 1px solid #边框色;
    border-radius: 3px;
    padding: 1px 18px 1px 3px;
    color: #文字色;
    font-family: "微软雅黑";
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;
    border-left-width: 1px;
    border-left-color: #边框色;
    border-left-style: solid;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}

QComboBox::down-arrow {
    image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA...);
}
```

### 3. 颜色规范
- 使用十六进制颜色代码
- 确保颜色对比度足够
- 保持主题色彩协调

### 4. 主题测试
- 测试所有控件显示效果
- 验证颜色对比度
- 确保文字清晰可读

---

## 数据管理规范

### 1. 文件存储规范

#### 便签数据文件
- 位置: `notes/note_{id}.json`
- 格式: UTF-8 编码的 JSON
- 备份: 建议定期备份 notes 目录

#### 配置文件
- 位置: `settings.json`
- 格式: UTF-8 编码的 JSON
- 默认值: 程序内置默认配置

### 2. 数据安全规范

#### 文件操作
- 使用异常处理包装文件操作
- 确保文件编码为 UTF-8
- 避免文件占用冲突

#### 数据验证
- 加载数据时验证 JSON 格式
- 提供默认值处理机制
- 处理文件不存在的情况

---

## 错误处理规范

### 1. 异常处理原则
- 使用 try-except 包装可能出错的操作
- 提供用户友好的错误提示
- 记录详细的错误信息用于调试

### 2. 常见错误处理

#### 文件操作错误
```python
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    # 文件不存在，使用默认值
    data = default_data()
except json.JSONDecodeError:
    # JSON 格式错误
    QMessageBox.warning(self, '数据错误', 'JSON 格式错误')
except Exception as e:
    # 其他错误
    QMessageBox.warning(self, '加载错误', f'无法加载文件: {e}')
```

#### 主题加载错误
```python
try:
    with open(theme_file, 'r', encoding='utf-8') as f:
        style = f.read()
        self.setStyleSheet(style)
except Exception as e:
    QMessageBox.warning(self, '样式加载错误', f'无法加载样式文件: {e}')
```

---

## 性能优化规范

### 1. 内存管理
- 及时释放不需要的对象
- 避免循环引用
- 合理使用缓存机制

### 2. 文件操作优化
- 减少频繁的文件读写
- 使用批量操作
- 异步处理耗时操作

### 3. UI 响应优化
- 避免在主线程执行耗时操作
- 使用信号槽机制
- 合理设置更新频率

---

## 测试规范

### 1. 功能测试
- 便签创建、编辑、删除
- 主题切换功能
- 系统托盘操作
- 开机自启设置

### 2. 兼容性测试
- Windows 10/11 兼容性
- 不同分辨率适配
- 多显示器支持

### 3. 压力测试
- 大量便签创建
- 长时间运行稳定性
- 内存泄漏检测

---

## 版本管理规范

### 1. 版本号规范
- 格式: `主版本.次版本.修订版本`
- 示例: `1.0.0`, `1.1.0`, `1.1.1`

### 2. 更新日志

#### Version 1.5.3 (2026年06月)
**功能优化**:
- ✅ MSI 安装目录选择自动追加 `StickyNote\` 子目录
- ✅ 安装完成后显示"立即运行程序"复选框

#### Version 1.5.2 (2026年06月)
**Bug 修复**:
- ✅ 修复便携版更新致命bug: `_match_asset()` 改为匹配 `.zip` 资产
- ✅ 修复更新安装无响应: `.bat` 替代 `.ps1`，消除 ExecutionPolicy 问题

**功能优化**:
- ✅ 统一下载策略: 所有安装类型均下载 ZIP，MSI 用户额外下载 MSI 仅用于注册表更新
- ✅ robocopy 替换: 带 `/R:3 /W:5` 重试机制，排除用户数据目录
- ✅ PID 等待机制: 使用 `tasklist /fi "PID eq {pid}"` 精确等待进程退出
- ✅ 可见控制台窗口: `CREATE_NEW_CONSOLE` 启动更新脚本
- ✅ 完善错误处理: 失败时 `pause` 等待用户查看，日志输出到 `%TEMP%\stickynote_update.log`

#### Version 1.5.1 (2026年06月)
**Bug 修复**:
- ✅ 修复设置中手动检查更新时卡死主界面的问题

**功能优化**:
- ✅ 更新检查改为后台 QThread 异步执行，不再阻塞主线程
- ✅ 增加检查更新进度条显示（不确定模式滚动条）
- ✅ 增加取消检查按钮，支持随时中止更新检查
- ✅ 增加状态文字提示（正在连接GitHub → 正在解析版本信息 → 完成）
- ✅ 版本检查超时时间调整为 30 秒（适配国内网络环境）
- ✅ 新增 features/updater.py 更新模块（UpdateChecker / UpdateDownloader / UpdateDialog）

#### Version 1.5.0 (2026年06月)
**功能优化**:
- ✅ 作者统一为 MaWenshui
- ✅ MSI 安装路径优化，自动追加 StickyNote 子目录
- ✅ 新增自动更新检测与下载功能（GitHub Release API）

#### Version 1.4.0 (2026年06月)
**架构改进**:
- ✅ 项目目录清理与构建路径规范化
- ✅ 新增 tests/ 测试模块（test_manager_integration.py, test_updater.py）
- ✅ 新增 tools/ 工具模块（generate_icon.py, uninstall.ps1）
- ✅ MSI 包更名为 StickyNote 避免中文文件名截断
- ✅ 引入 cx_Freeze 替代 PyInstaller 打包

#### Version 1.3.1 (2026年06月)
**Bug 修复**:
- ✅ toggle_always_on_top 复选框状态同步修复
- ✅ 透明度菜单 QActionGroup 互斥修复

**文档更新**:
- ✅ 更新 PROJECT_SPECIFICATION.md 至 v1.3.1
- ✅ 更新 readme.md 功能特性和快捷键
- ✅ 更新 IMPROVEMENT_PLAN.md 标记完成状态

#### Version 1.3.0 (2026年06月)
**新增功能**:
- ✅ 右键上下文菜单 (复制粘贴/主题/字体/置顶/透明度/标签/提醒)
- ✅ 窗口吸附 (屏幕边缘 + 便签间边缘对齐)
- ✅ 淡入淡出动画 (200ms淡入/150ms淡出)

**性能优化**:
- ✅ 异步I/O保存 (NoteSaveWorker 后台线程)
- ✅ 异步I/O加载 (NoteLoadWorker 后台线程)
- ✅ 保存防抖 (500ms 延迟)
- ✅ 核心模块拆分 (main.py → core/note.py + core/manager.py + core/settings.py)

#### Version 1.2.0 (2025年06月)
**新增功能**:
- ✅ 定时提醒系统 (一次性/每天/每周/每月，系统托盘通知)
- ✅ 标签管理 (CRUD/颜色/分组/芯片组件)
- ✅ 导入导出 (TXT/Markdown/ZIP)
- ✅ 模板系统 (5个内置模板 + 自定义)
- ✅ 智能格式化粘贴 (JSON/HTML/Markdown等8种格式)
- ✅ 富文本格式工具栏 (加粗、斜体、字体颜色)
- ✅ 选择性文本格式应用
- ✅ 字体颜色自定义选择
- ✅ HTML格式便签内容存储
- ✅ 纯文本内容备份机制

**功能增强**:
- ✅ 字体大小调整功能修复 (A+/A-按钮)
- ✅ 标题栏高度自适应调整
- ✅ 托盘菜单扩展 (标签分组/导入导出/从模板创建)

**技术改进**:
- ✅ QTextCharFormat富文本格式支持
- ✅ HTML内容加载和保存机制
- ✅ 格式状态实时同步
- ✅ 主题系统兼容性增强

#### Version 1.1.0 (2025年06月)
**新增功能**:
- ✅ 便签搜索功能 (Ctrl+Shift+F)
- ✅ 撤销/重做操作支持 (Ctrl+Z/Ctrl+Y)
- ✅ 全局快捷键系统 (Ctrl+Shift+N/F/B)
- ✅ 智能窗口定位
- ✅ 数据备份管理 (Ctrl+Shift+B)

**架构改进**:
- ✅ 新增 features/ 模块化架构
- ✅ 功能管理器模式实现
- ✅ 增强的编辑器组件

#### Version 1.0.0 (2024年11月)
**基础功能**:
- 便签创建、编辑、删除
- 多主题支持
- 系统托盘集成
- 开机自启动
- 窗口透明度调节
- 字体大小调节

### 3. 发布流程
1. 代码审查
2. 功能测试
3. 文档更新
4. 版本打包
5. 发布部署

---

## 安全规范

### 1. 数据安全
- 用户数据本地存储
- 避免敏感信息泄露
- 文件权限控制

### 2. 系统安全
- 注册表操作权限控制
- 避免恶意代码注入
- 安全的文件路径处理

---

## 扩展开发指南

### 1. 新功能扩展

#### 添加新的便签功能
1. 在 `StickyNote` 类中添加新方法
2. 更新 UI 布局
3. 修改数据结构
4. 更新保存/加载逻辑

#### 添加新的功能模块 (Version 1.1.0架构)
1. 在 `features/` 目录下创建新的模块文件
2. 实现功能管理器类
3. 在 `StickyNoteManager` 中初始化管理器
4. 添加相应的UI对话框
5. 集成到托盘菜单和快捷键系统

#### 添加新的主题元素
1. 在 CSS 文件中添加新的样式规则
2. 更新主题加载逻辑
3. 测试主题兼容性

#### 添加新的全局快捷键
1. 在 `ShortcutManager` 中注册新快捷键
2. 实现对应的处理方法
3. 更新托盘菜单显示
4. 添加快捷键冲突检测

### 2. 模块化架构指南 (Version 1.1.0)

#### 功能管理器模式
- 每个功能模块实现独立的管理器类
- 管理器负责功能的初始化、配置和清理
- 通过信号槽机制与主程序通信

#### 模块文件结构
```python
# features/new_feature.py
class NewFeatureManager:
    def __init__(self, parent=None):
        self.parent = parent
        self.setup_ui()
    
    def setup_ui(self):
        # 初始化UI组件
        pass
    
    def show_dialog(self):
        # 显示功能对话框
        pass
    
    def cleanup(self):
        # 清理资源
        pass
```

### 3. 插件系统设计
- 定义插件接口
- 实现插件加载机制
- 提供插件开发文档

---

## 维护指南

### 1. 日常维护
- 定期检查代码质量
- 更新依赖库版本
- 修复已知 bug

### 2. 用户反馈处理
- 建立反馈收集机制
- 及时响应用户问题
- 持续改进用户体验

### 3. 文档维护
- 保持文档与代码同步
- 定期更新使用手册
- 完善开发文档

---

## 总结

本项目规范文档为 StickyNote 项目的开发、维护和扩展提供了全面的指导。从 v1.0.0 到 v1.5.3，项目经历了模块化架构重构、功能扩展、性能优化、自动更新和安装体验优化五个主要阶段，现已拥有 18 个 Python 模块、10 种主题样式、11 个功能子系统的完善桌面便签应用。

### 各版本主要成就

#### v1.1.0 — 模块化架构
- ✅ features/ 目录引入，功能模块化管理
- ✅ 搜索功能、撤销/重做、全局快捷键、智能定位、数据备份

#### v1.2.0 — 高级功能
- ✅ 定时提醒、标签管理、导入导出、模板系统、智能格式化
- ✅ 富文本格式工具栏（加粗/斜体/字体颜色）

#### v1.3.0 / v1.3.1 — UI/性能
- ✅ 右键上下文菜单、窗口吸附、淡入淡出动画
- ✅ 异步I/O加载/保存、核心模块拆分 (core/)
- ✅ Bug修复：复选框状态同步、透明度菜单互斥

#### v1.4.0 — 构建优化
- ✅ 项目目录清理、构建路径规范化
- ✅ cx_Freeze 打包方案、MSI 规范化命名
- ✅ 新增 tests/ 和 tools/ 模块

#### v1.5.0 ~ v1.5.3 — 自动更新与安装体验
- ✅ GitHub Release API 自动更新检测与下载
- ✅ 更新检查异步化，不阻塞主界面
- ✅ 进度条、取消按钮、状态提示
- ✅ 30秒超时适配国内网络
- ✅ 统一 ZIP 更新策略 + robocopy + PID 等待
- ✅ MSI 安装目录自动追加子目录 + 安装后运行提示

### 技术架构优势
- **模块化**: core/ + features/ 双层架构，16个模块分工明确
- **可扩展性**: 功能管理器模式，新增功能只需添加 features/ 模块
- **可维护性**: 清晰的代码结构和命名规范
- **性能**: 异步I/O + 防抖保存，UI主线程不阻塞
- **用户体验**: 动画效果、窗口吸附、右键菜单、多主题
- **稳定性**: 完善的错误处理和数据保护

### 模块清单 (共16个)
| 模块 | 文件 | 版本 | 职责 |
|------|------|------|------|
| 主入口 | main.py | 1.0.0 | 程序入口 |
| 核心导出 | core/__init__.py | 1.5.3 | 版本管理和导出 |
| 便签组件 | core/note.py | 1.5.3 | 窗口UI/动画/吸附/I/O |
| 应用管理 | core/manager.py | 1.5.2 | 生命周期/托盘/集成 |
| 设置对话框 | core/settings.py | 1.3.0 | 主题和字体设置 |
| 搜索 | features/search.py | 1.1.0 | 全文搜索 |
| 备份 | features/backup.py | 1.1.0 | 自动/手动备份 |
| 快捷键 | features/shortcuts.py | 1.1.0 | 全局热键 |
| 定位 | features/positioning.py | 1.1.0 | 智能窗口布局 |
| 撤销重做 | features/undo_redo.py | 1.1.0 | Ctrl+Z/Y |
| 格式化 | features/formatter.py | 1.2.0 | 智能粘贴 |
| 提醒 | features/reminder.py | 1.2.0 | 定时通知 |
| 标签 | features/tag.py | 1.2.0 | 分类管理 |
| 导入导出 | features/import_export.py | 1.2.0 | TXT/MD/ZIP |
| 模板 | features/template.py | 1.2.0 | 快速创建 |
| 自动更新 | features/updater.py | 1.5.2 | GitHub版本检测/下载/安装 |
| 功能导出 | features/__init__.py | 1.5.3 | 模块元信息 |

### 联系信息
- **开发者**: MaWenshui
- **项目地址**: [项目仓库地址]
- **问题反馈**: [反馈邮箱或地址]

---

*最后更新时间: 2026年6月*
*文档版本: 1.5.3*
*对应软件版本: StickyNote 1.5.3*
*更新内容: 新增 v1.5.2 ~ v1.5.3 版本日志、MSI 安装体验优化，完善模块清单*