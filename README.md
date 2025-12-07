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
- 📄 **Single-File Mode** - All prompts in one `prompts.yaml` (default, clean and simple)
- 📂 **Multi-File Mode** - Separate files per prompt (for large projects)
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
# Single-file mode (default) - creates prompts.yaml
pvcs init

# Multi-file mode - creates prompts/ directory
pvcs init --split
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

# Clean mode: extract prompts to YAML and remove from code
pvcs migrate src/ --clean -y
```

**Supported Conversions:**

```python
# Before
prompt = f"Hello {user.name}, price: {price:.2f}"

# After (default mode)
from prompt_vcs import p
prompt = p("demo_prompt", "Hello {user_name}, price: {price:.2f}", 
           user_name=user.name, price=price)

# After (--clean mode)
from prompt_vcs import p
prompt = p("demo_prompt", user_name=user.name, price=price)
# + creates prompts/demo_prompt/v1.yaml with the template
```

**Features:**
- ✅ F-string variable extraction
- ✅ Format spec preservation (`:.2f`)
- ✅ Attribute/dict access sanitization (`user.name` → `user_name`)
- ✅ Automatic import statement insertion
- ✅ Smart skipping of short strings and complex expressions
- ✅ **Clean mode**: Extract to YAML, keep only ID in code

## 📁 Project Structure

### Single-File Mode (Default)

```
your-project/
├── .prompt_lock.json     # Version lock file
├── prompts.yaml          # All prompts in one file
└── src/
    └── your_code.py
```

**prompts.yaml format:**
```yaml
user_greeting:
  description: "Greeting template"
  template: |
    Hello, {name}!

system_core:
  description: "System prompt"
  template: |
    You are a helpful assistant.
```

### Multi-File Mode (--split)

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
| `pvcs init` | Initialize project (single-file mode, creates prompts.yaml) |
| `pvcs init --split` | Initialize project (multi-file mode, creates prompts/ dir) |
| `pvcs scaffold <dir>` | Scan code and generate prompts (auto-detects mode) |
| `pvcs switch <id> <version>` | Switch prompt version |
| `pvcs status` | View current lock status |
| `pvcs migrate <path>` | Auto-migrate hardcoded prompts |
| `pvcs migrate <path> --clean` | Migrate and extract prompts to YAML files |

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 👤 Author

**emerard** - [@Dreamer431](https://github.com/Dreamer431)
