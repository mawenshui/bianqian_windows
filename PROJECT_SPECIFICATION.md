# StickyNote 项目规范文档

## 项目概述

**StickyNote** 是一款基于 PyQt5 开发的 Windows 桌面便签应用程序，提供便签创建、编辑、管理和主题自定义等功能。本项目采用面向对象设计，支持多便签管理、系统托盘集成、开机自启动等特性。

### 项目信息
- **项目名称**: StickyNote
- **开发语言**: Python 3.x
- **GUI框架**: PyQt5
- **目标平台**: Windows 10+
- **开发者**: MaWenshui
- **版本**: 1.0

---

## 项目架构

### 目录结构
```
bianqian_windows/
├── main.py                 # 主程序入口文件
├── settings.json           # 应用配置文件
├── readme.md              # 用户使用手册
├── PROJECT_SPECIFICATION.md # 项目规范文档（本文件）
├── notes/                 # 便签数据存储目录（运行时创建）
│   ├── note_1.json       # 便签数据文件
│   ├── note_2.json
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

#### 1. 主程序模块 (main.py)
- **StickyNoteManager**: 应用程序管理器类
- **StickyNote**: 便签窗口类
- **SettingsDialog**: 设置对话框类
- **PlainTextEdit**: 自定义文本编辑器
- **PlainLineEdit**: 自定义单行编辑器

#### 2. 数据存储模块
- **便签数据**: JSON格式存储在 `notes/` 目录
- **应用设置**: JSON格式存储在 `settings.json`

#### 3. 主题系统模块
- **CSS样式文件**: 存储在 `styles/` 目录
- **主题管理**: 动态加载和应用主题

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
- 字体大小调节
- 总在最前设置

#### 数据结构
```json
{
    "title": "便签标题",
    "content": "便签内容",
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
    "content_font_size": 12
}
```

### 2. 系统托盘模块

#### 功能特性
- 托盘图标显示
- 右键菜单管理
- 便签列表显示
- 快速操作入口
- 双击打开便签

#### 菜单结构
- 添加便签
- 便签列表（子菜单）
  - 便签标题
    - 打开
    - 删除
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

### 4. 设置管理模块

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
- 记录每个版本的变更内容
- 包含新功能、bug修复、性能优化
- 提供升级指导

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

#### 添加新的主题元素
1. 在 CSS 文件中添加新的样式规则
2. 更新主题加载逻辑
3. 测试主题兼容性

### 2. 插件系统设计
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

本项目规范文档为 StickyNote 项目的开发、维护和扩展提供了全面的指导。开发者应严格遵循本规范，确保代码质量、项目稳定性和用户体验。随着项目的发展，本规范也将持续更新和完善。

### 联系信息
- **开发者**: MaWenshui
- **项目地址**: [项目仓库地址]
- **问题反馈**: [反馈邮箱或地址]

---

*最后更新时间: 2024年12月*
*文档版本: 1.0*