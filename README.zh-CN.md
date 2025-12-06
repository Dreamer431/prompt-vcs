# prompt-vcs

[![PyPI version](https://badge.fury.io/py/prompt-vcs.svg)](https://badge.fury.io/py/prompt-vcs)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Git 原生的 LLM Prompt 管理库

一个轻量级、代码优先的 Python 库，基于 Git 和文件系统管理 LLM Prompts，无需外部数据库。

[English](README.md)

## ✨ 特性

- 🚀 **零配置启动** - 直接在代码中定义 Prompt，无需额外设置
- 📦 **Git 原生** - 使用文件系统和 Git 进行版本控制
- 🔄 **Lockfile 机制** - 生产环境锁定特定版本，开发环境使用代码字符串
- 🛠️ **自动迁移** - 一键将现有硬编码 Prompt 转换为可管理格式
- 🎯 **类型安全** - 完整的类型提示支持

## 📦 安装

```bash
pip install prompt-vcs
```

## 🚀 快速开始

### 1. 初始化项目

```bash
pvcs init
```

### 2. 内联模式

```python
from prompt_vcs import p

# 默认使用代码中的字符串，lockfile 锁定后使用对应版本
msg = p("user_greeting", "你好 {name}", name="开发者")
```

### 3. 装饰器模式

```python
from prompt_vcs import prompt

@prompt(id="system_core", default_version="v1")
def get_system_prompt(role: str):
    """
    你是一个乐于助人的助手，扮演的角色是 {role}。
    """
    pass
```

### 4. 提取 Prompt 为 YAML

```bash
pvcs scaffold src/
```

### 5. 切换版本

```bash
pvcs switch user_greeting v2
```

### 6. 自动迁移现有代码

将硬编码的 prompt 字符串自动转换为 `p()` 调用：

```bash
# 预览变更
pvcs migrate src/ --dry-run

# 交互式迁移（逐个确认）
pvcs migrate src/

# 自动应用所有变更
pvcs migrate src/ --yes

# 纯配置模式：提取 prompt 到 YAML，代码中只保留 ID
pvcs migrate src/ --clean -y
```

**支持的转换：**

```python
# 转换前
prompt = f"Hello {user.name}, 价格: {price:.2f}"

# 转换后（默认模式）
from prompt_vcs import p
prompt = p("demo_prompt", "Hello {user_name}, 价格: {price:.2f}", 
           user_name=user.name, price=price)

# 转换后（--clean 模式）
from prompt_vcs import p
prompt = p("demo_prompt", user_name=user.name, price=price)
# + 自动创建 prompts/demo_prompt/v1.yaml
```

**特性：**
- ✅ f-string 变量提取
- ✅ 格式化符号保留 (`:.2f`)
- ✅ 属性/字典访问自动清洗 (`user.name` → `user_name`)
- ✅ 自动添加导入语句
- ✅ 智能跳过短字符串和复杂表达式
- ✅ **纯配置模式**：提取到 YAML，代码中只保留 ID

## 📁 项目结构

```
your-project/
├── .prompt_lock.json     # 版本锁定文件
├── prompts/              # Prompt YAML 文件
│   ├── user_greeting/
│   │   ├── v1.yaml
│   │   └── v2.yaml
│   └── system_core/
│       └── v1.yaml
└── src/
    └── your_code.py
```

## 🎯 核心理念

- **无数据库**: 文件系统就是数据库
- **Git 原生**: 版本控制依赖文件命名规范和 Git 提交
- **代码优先**: 开发者首先在代码中定义 Prompt
- **零延迟开发**: 开发模式使用代码中的字符串，生产模式读取 Lockfile

## 📖 CLI 命令

| 命令 | 说明 |
|------|------|
| `pvcs init` | 初始化项目（创建 lockfile 和 prompts 目录） |
| `pvcs scaffold <dir>` | 扫描代码并生成 YAML 文件 |
| `pvcs switch <id> <version>` | 切换 Prompt 版本 |
| `pvcs status` | 查看当前锁定状态 |
| `pvcs migrate <path>` | 自动迁移硬编码 Prompt |
| `pvcs migrate <path> --clean` | 迁移并提取 Prompt 到 YAML 文件 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License - 详见 [LICENSE](LICENSE) 文件

## 👤 作者

**emerard** - [@Dreamer431](https://github.com/Dreamer431)
