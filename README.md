# prompt-vcs

[![PyPI version](https://img.shields.io/pypi/v/prompt-vcs.svg)](https://img.shields.io/pypi/v/prompt-vcs.svg)
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
- 🧪 **Testing Framework** - Define and run test cases for prompts with YAML-based test suites
- ✅ **Output Validation** - Validate prompt outputs with JSON schema, regex, length checks, and custom rules
- 🔬 **A/B Testing** - Compare different prompt versions and analyze LLM output effectiveness
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
# - If prompts.yaml exists → writes to prompts.yaml (single-file mode)
# - Otherwise → creates prompts/{id}/v1.yaml (multi-file mode)
pvcs migrate src/ --clean -y
```

**Supported Conversions:**

```python
# Before
prompt = f"Hello {user.name}, price: {price:.2f}"

# After (default mode) - keeps template in code
from prompt_vcs import p
prompt = p("demo_prompt", "Hello {user_name}, price: {price:.2f}", 
           user_name=user.name, price=price)

# After (--clean mode) - extracts template to YAML
from prompt_vcs import p
prompt = p("demo_prompt", user_name=user.name, price=price)
# Template is stored in prompts.yaml or prompts/demo_prompt/v1.yaml
```

**Features:**
- ✅ F-string variable extraction
- ✅ Format spec preservation (`:.2f`)
- ✅ Attribute/dict access sanitization (`user.name` → `user_name`)
- ✅ Automatic import statement insertion
- ✅ Smart skipping of short strings and complex expressions
- ✅ **Clean mode**: Extract to YAML, keep only ID in code
- ✅ **Auto-detects storage mode**: single-file (`prompts.yaml`) or multi-file (`prompts/`)

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

## 🧪 Testing Framework

Define test cases in YAML and validate prompt outputs:

```yaml
# tests/prompts_test.yaml
name: "Prompt Tests"
tests:
  - name: "greeting_test"
    prompt_id: "user_greeting"
    inputs:
      name: "Developer"
    expected_output: "Hello, Developer!"
    validation:
      - type: contains
        substring: "Hello"
      - type: length
        max_length: 100
```

```python
from prompt_vcs.testing import PromptTestRunner, load_test_suite_from_yaml

# Load and run tests
suite = load_test_suite_from_yaml("tests/prompts_test.yaml")
runner = PromptTestRunner()
results = runner.run_suite(suite)
```

**Validation Types:**
- `json_schema` - Validate JSON structure (requires `pip install prompt-vcs[validation]`)
- `regex` - Match patterns
- `length` - Check min/max length
- `contains` - Verify substring presence
- `custom` - Custom validation functions

## 🔬 A/B Testing

Compare different prompt versions and analyze their effectiveness:

```python
from prompt_vcs import ABTestManager, ABTestConfig, ABTestVariant

# Create an experiment
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

# Run experiment
with manager.experiment("greeting_test") as exp:
    prompt = exp.get_prompt(name="Alice")
    response = my_llm.generate(prompt)  # Your LLM call
    exp.record(output=response, score=0.8)

# Analyze results
result = manager.analyze("greeting_test")
print(result.summary())
```

**CLI Commands:**

```bash
# Create an A/B test experiment
pvcs ab create my_test user_greeting --variants v1,v2

# List all experiments
pvcs ab list

# View experiment status
pvcs ab status my_test

# Manually record a result
pvcs ab record my_test v1 --score 0.8

# Analyze results
pvcs ab analyze my_test
```

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
| `pvcs test <suite.yaml>` | Run prompt tests from YAML suite |
| `pvcs diff <id> <v1> <v2>` | Compare two versions of a prompt |
| `pvcs log <id>` | Show Git commit history for a prompt |
| `pvcs ab create <name> <id>` | Create an A/B test experiment |
| `pvcs ab list` | List all A/B test experiments |
| `pvcs ab status <name>` | View experiment status and variants |
| `pvcs ab analyze <name>` | Analyze experiment results |
| `pvcs ab record <name> <v>` | Manually record a test result |

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 👤 Author

**emerard** - [@Dreamer431](https://github.com/Dreamer431)
