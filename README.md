# prompt-vcs

[![PyPI version](https://badge.fury.io/py/prompt-vcs.svg)](https://badge.fury.io/py/prompt-vcs)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Git-native prompt management library for LLM applications

A lightweight, code-first Python library for managing LLM prompts using Git and the file system — no external database required.

[中文文档](README.zh-CN.md)

## ✨ Features

- 🚀 **Zero Configuration** - Define prompts directly in code, no extra setup needed
- 📦 **Git Native** - Version control through file system and Git
- 🔄 **Lockfile Mechanism** - Lock specific versions for production, use code strings in development
- 🛠️ **Auto Migration** - One-click conversion of hardcoded prompts to managed format
- 🎯 **Type Safe** - Full type hints support

## 📦 Installation

```bash
pip install prompt-vcs
```

## 🚀 Quick Start

### 1. Initialize Project

```bash
pvcs init
```

### 2. Inline Mode

```python
from prompt_vcs import p

# Uses code string by default, switches to locked version when specified
msg = p("user_greeting", "Hello {name}", name="Developer")
```

### 3. Decorator Mode

```python
from prompt_vcs import prompt

@prompt(id="system_core", default_version="v1")
def get_system_prompt(role: str):
    """
    You are a helpful assistant playing the role of {role}.
    """
    pass
```

### 4. Extract Prompts to YAML

```bash
pvcs scaffold src/
```

### 5. Switch Versions

```bash
pvcs switch user_greeting v2
```

### 6. Auto-Migrate Existing Code

Automatically convert hardcoded prompt strings to `p()` calls:

```bash
# Preview changes
pvcs migrate src/ --dry-run

# Interactive migration (confirm each change)
pvcs migrate src/

# Apply all changes automatically
pvcs migrate src/ --yes
```

**Supported Conversions:**

```python
# Before
prompt = f"Hello {user.name}, price: {price:.2f}"

# After
from prompt_vcs import p
prompt = p("demo_prompt", "Hello {user_name}, price: {price:.2f}", 
           user_name=user.name, price=price)
```

**Features:**
- ✅ F-string variable extraction
- ✅ Format spec preservation (`:.2f`)
- ✅ Attribute/dict access sanitization (`user.name` → `user_name`)
- ✅ Automatic import statement insertion
- ✅ Smart skipping of short strings and complex expressions

## 📁 Project Structure

```
your-project/
├── .prompt_lock.json     # Version lock file
├── prompts/              # Prompt YAML files
│   ├── user_greeting/
│   │   ├── v1.yaml
│   │   └── v2.yaml
│   └── system_core/
│       └── v1.yaml
└── src/
    └── your_code.py
```

## 🎯 Core Principles

- **No Database** - File system is the database
- **Git Native** - Version control relies on file naming conventions and Git commits
- **Code First** - Developers define prompts in code first
- **Zero Latency Dev** - Development mode uses code strings, production reads from Lockfile

## 📖 CLI Commands

| Command | Description |
|---------|-------------|
| `pvcs init` | Initialize project (create lockfile and prompts directory) |
| `pvcs scaffold <dir>` | Scan code and generate YAML files |
| `pvcs switch <id> <version>` | Switch prompt version |
| `pvcs status` | View current lock status |
| `pvcs migrate <path>` | Auto-migrate hardcoded prompts |

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 👤 Author

**emerard** - [@Dreamer431](https://github.com/Dreamer431)
