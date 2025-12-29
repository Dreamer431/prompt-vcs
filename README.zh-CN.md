# prompt-vcs

[![PyPI version](https://img.shields.io/pypi/v/prompt-vcs.svg)](https://img.shields.io/pypi/v/prompt-vcs.svg)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Git 原生的 LLM Prompt 管理库

一个轻量级、代码优先的 Python 库，基于 Git 和文件系统管理 LLM Prompts，无需外部数据库。

[English](README.md)

## ✨ 特性

- 🚀 **零配置启动** - 直接在代码中定义 Prompt，无需额外设置
- 📦 **Git 原生** - 使用文件系统和 Git 进行版本控制
- 📄 **单文件模式** - 所有 Prompt 存放在一个 `prompts.yaml` 文件中（默认，简洁清爽）
- 📂 **多文件模式** - 每个 Prompt 单独一个文件（适合大型项目）
- 🔄 **Lockfile 机制** - 生产环境锁定特定版本，开发环境使用代码字符串
- 🛠️ **自动迁移** - 一键将现有硬编码 Prompt 转换为可管理格式
- 🧪 **测试框架** - 使用 YAML 定义测试用例并运行 Prompt 测试
- ✅ **输出验证** - 支持 JSON Schema、正则表达式、长度检查和自定义规则验证
- 🔬 **A/B 测试** - 对比不同版本 Prompt 的效果，分析 LLM 输出质量
- 🎯 **类型安全** - 完整的类型提示支持

## 📦 安装

```bash
pip install prompt-vcs
```

## 🚀 快速开始

### 1. 初始化项目

```bash
# 单文件模式（默认）- 创建 prompts.yaml
pvcs init

# 多文件模式 - 创建 prompts/ 目录
pvcs init --split
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
# - 如果存在 prompts.yaml → 写入 prompts.yaml（单文件模式）
# - 否则 → 创建 prompts/{id}/v1.yaml（多文件模式）
pvcs migrate src/ --clean -y
```

**支持的转换：**

```python
# 转换前
prompt = f"Hello {user.name}, 价格: {price:.2f}"

# 转换后（默认模式）- 模板保留在代码中
from prompt_vcs import p
prompt = p("demo_prompt", "Hello {user_name}, 价格: {price:.2f}", 
           user_name=user.name, price=price)

# 转换后（--clean 模式）- 模板提取到 YAML
from prompt_vcs import p
prompt = p("demo_prompt", user_name=user.name, price=price)
# 模板存储在 prompts.yaml 或 prompts/demo_prompt/v1.yaml 中
```

**特性：**
- ✅ f-string 变量提取
- ✅ 格式化符号保留 (`:.2f`)
- ✅ 属性/字典访问自动清洗 (`user.name` → `user_name`)
- ✅ 自动添加导入语句
- ✅ 智能跳过短字符串和复杂表达式
- ✅ **纯配置模式**：提取到 YAML，代码中只保留 ID
- ✅ **自动检测存储模式**：单文件 (`prompts.yaml`) 或多文件 (`prompts/`)

## 📁 项目结构

### 单文件模式（默认）

```
your-project/
├── .prompt_lock.json     # 版本锁定文件
├── prompts.yaml          # 所有 Prompt 存放在一个文件
└── src/
    └── your_code.py
```

**prompts.yaml 格式：**
```yaml
user_greeting:
  description: "问候语模板"
  template: |
    你好，{name}！

system_core:
  description: "系统提示词"
  template: |
    你是一个乐于助人的助手。
```

### 多文件模式 (--split)

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

## 🧪 测试框架

使用 YAML 定义测试用例并验证 Prompt 输出：

```yaml
# tests/prompts_test.yaml
name: "Prompt 测试"
tests:
  - name: "greeting_test"
    prompt_id: "user_greeting"
    inputs:
      name: "开发者"
    expected_output: "你好，开发者！"
    validation:
      - type: contains
        substring: "你好"
      - type: length
        max_length: 100
```

```python
from prompt_vcs.testing import PromptTestRunner, load_test_suite_from_yaml

# 加载并运行测试
suite = load_test_suite_from_yaml("tests/prompts_test.yaml")
runner = PromptTestRunner()
results = runner.run_suite(suite)
```

**验证类型：**
- `json_schema` - 验证 JSON 结构（需要 `pip install prompt-vcs[validation]`）
- `regex` - 正则表达式匹配
- `length` - 检查最小/最大长度
- `contains` - 验证是否包含子字符串
- `custom` - 自定义验证函数

## 🔬 A/B 测试

对比不同版本 Prompt 的效果并分析它们的有效性：

```python
from prompt_vcs import ABTestManager, ABTestConfig, ABTestVariant

# 创建实验
manager = ABTestManager.get_instance()
config = ABTestConfig(
    name="greeting_test",
    prompt_id="user_greeting",
    variants=[
        ABTestVariant("v1", weight=1.0),
        ABTestVariant("v2", weight=1.0),
    ],
)
manager.create_experiment(config)

# 运行实验
with manager.experiment("greeting_test") as exp:
    prompt = exp.get_prompt(name="Alice")
    response = my_llm.generate(prompt)  # 你的 LLM 调用
    exp.record(output=response, score=0.8)

# 分析结果
result = manager.analyze("greeting_test")
print(result.summary())
```

**CLI 命令：**

```bash
# 创建 A/B 测试实验
pvcs ab create my_test user_greeting --variants v1,v2

# 列出所有实验
pvcs ab list

# 查看实验状态
pvcs ab status my_test

# 手动记录结果
pvcs ab record my_test v1 --score 0.8

# 分析结果
pvcs ab analyze my_test
```

## 📖 CLI 命令

| 命令 | 说明 |
|------|------|
| `pvcs init` | 初始化项目（单文件模式，创建 prompts.yaml） |
| `pvcs init --split` | 初始化项目（多文件模式，创建 prompts/ 目录） |
| `pvcs scaffold <dir>` | 扫描代码并生成 Prompt（自动检测模式） |
| `pvcs switch <id> <version>` | 切换 Prompt 版本 |
| `pvcs status` | 查看当前锁定状态 |
| `pvcs migrate <path>` | 自动迁移硬编码 Prompt |
| `pvcs migrate <path> --clean` | 迁移并提取 Prompt 到 YAML 文件 |
| `pvcs test <suite.yaml>` | 从 YAML 测试套件运行 Prompt 测试 |
| `pvcs diff <id> <v1> <v2>` | 比较两个版本的 Prompt 差异 |
| `pvcs log <id>` | 查看 Prompt 的 Git 提交历史 |
| `pvcs ab create <name> <id>` | 创建 A/B 测试实验 |
| `pvcs ab list` | 列出所有 A/B 测试实验 |
| `pvcs ab status <name>` | 查看实验状态和变体 |
| `pvcs ab analyze <name>` | 分析实验结果 |
| `pvcs ab record <name> <v>` | 手动记录测试结果 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License - 详见 [LICENSE](LICENSE) 文件

## 👤 作者

**emerard** - [@Dreamer431](https://github.com/Dreamer431)
