# Prompt Validation and Testing Framework

This document describes the validation and testing framework for prompt-vcs.

## Overview

The validation and testing framework provides tools to:

1. **Validate prompt outputs** against defined schemas and rules
2. **Define test cases** for your prompts with inputs and expected outputs
3. **Run test suites** to ensure prompts work correctly
4. **Integrate testing** into your CI/CD pipeline

## Features

### 1. Validation Types

The framework supports multiple validation types:

- **Length Validation**: Check if output is within acceptable character limits
- **Regex Validation**: Validate output against regular expression patterns
- **Contains Validation**: Ensure output contains specific keywords
- **JSON Schema Validation**: Validate structured JSON outputs (requires `jsonschema` package)
- **Custom Validation**: Define your own validation logic

### 2. Test Framework

- Define test cases in YAML files
- Organize tests into suites
- Filter tests by tags
- Skip tests with reasons
- Get detailed test reports

## Installation

The validation and testing features are included in prompt-vcs. For JSON Schema validation, install the optional dependency:

```bash
pip install jsonschema
```

## Quick Start

### Defining Validation Rules

Create a validation config file (`validation_config.yaml`):

```yaml
validation:
  - type: length
    name: reasonable_length
    min_length: 10
    max_length: 1000

  - type: contains
    name: has_greeting
    substring: "Hello"

  - type: regex
    name: has_email
    pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
```

### Running Validation

Use the CLI to validate prompt outputs:

```bash
pvcs validate user_greeting "Hello, Alice!" --config validation_config.yaml
```

### Defining Test Cases

Create a test suite file (`test_suite.yaml`):

```yaml
name: "Greeting Tests"
description: "Tests for greeting prompts"

tests:
  - prompt_id: "user_greeting"
    name: "test_greeting_alice"
    inputs:
      name: "Alice"
    validation:
      - type: contains
        substring: "Alice"
      - type: length
        min_length: 5
        max_length: 100

  - prompt_id: "user_greeting"
    name: "test_exact_output"
    inputs:
      name: "Bob"
    expected_output: "Hello, Bob!"
```

### Running Tests

Execute tests using the CLI:

```bash
# Run all tests
pvcs test test_suite.yaml

# Run tests with a specific tag
pvcs test test_suite.yaml --tag smoke

# Verbose output
pvcs test test_suite.yaml --verbose
```

## Programmatic Usage

### Using Validators in Code

```python
from prompt_vcs import PromptValidator, ValidationRule, ValidationType

# Create validator
validator = PromptValidator()

# Add rules
validator.add_rule(ValidationRule(
    rule_type=ValidationType.LENGTH,
    name="length_check",
    min_length=10,
    max_length=100,
))

validator.add_rule(ValidationRule(
    rule_type=ValidationType.CONTAINS,
    name="keyword_check",
    substring="important",
))

# Validate output
results = validator.validate("This is an important message.")

for result in results:
    if result.passed:
        print(f"✓ {result.rule_name}")
    else:
        print(f"✗ {result.rule_name}: {result.error_message}")
```

### Custom Validation

```python
from prompt_vcs import ValidationRule, ValidationType

def is_polite(text: str) -> bool:
    polite_words = ["please", "thank you", "welcome"]
    return any(word in text.lower() for word in polite_words)

validator.add_rule(ValidationRule(
    rule_type=ValidationType.CUSTOM,
    name="politeness",
    custom_validator=is_polite,
    error_message="Text should be polite",
))
```

### Running Tests Programmatically

```python
from pathlib import Path
from prompt_vcs.testing import (
    load_test_suite_from_yaml,
    PromptTestRunner,
    TestReporter,
)

# Load test suite
suite = load_test_suite_from_yaml(Path("test_suite.yaml"))

# Run tests
runner = PromptTestRunner()
results = runner.run_suite(suite)

# Print results
TestReporter.print_detailed(results, verbose=True)
TestReporter.print_summary(results)
```

## Validation Rule Reference

### Length Validation

```yaml
- type: length
  name: "length_check"
  min_length: 10      # Optional
  max_length: 1000    # Optional
  error_message: "Custom error message"
```

### Regex Validation

```yaml
- type: regex
  name: "pattern_check"
  pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
  error_message: "Must contain valid email"
```

### Contains Validation

```yaml
- type: contains
  name: "keyword_check"
  substring: "important"
  error_message: "Must contain keyword"
```

### JSON Schema Validation

```yaml
- type: json_schema
  name: "schema_check"
  schema:
    type: object
    properties:
      name:
        type: string
      age:
        type: number
    required:
      - name
  error_message: "Invalid JSON structure"
```

## Test Case Reference

### Basic Test Case

```yaml
- prompt_id: "greeting"
  name: "test_greeting"
  inputs:
    name: "Alice"
  expected_output: "Hello, Alice!"
```

### Test with Validation

```yaml
- prompt_id: "greeting"
  name: "test_with_validation"
  inputs:
    name: "Bob"
  validation:
    - type: contains
      substring: "Bob"
    - type: length
      min_length: 5
```

### Tagged Test

```yaml
- prompt_id: "greeting"
  name: "smoke_test"
  tags:
    - smoke
    - quick
  inputs:
    name: "Test"
  expected_output: "Hello, Test!"
```

### Skipped Test

```yaml
- prompt_id: "new_feature"
  name: "test_new_feature"
  skip: true
  skip_reason: "Feature not implemented yet"
```

## Best Practices

1. **Organize Tests**: Group related tests in the same suite
2. **Use Tags**: Tag tests for easy filtering (smoke, integration, etc.)
3. **Descriptive Names**: Use clear test names that describe what they test
4. **Validation Over Exact Match**: Prefer validation rules over exact output matching for flexibility
5. **CI Integration**: Run tests in your CI pipeline to catch regressions

## Examples

See the `examples/` directory for complete examples:

- `validation_config.yaml` - Example validation configuration
- `test_suite.yaml` - Example test suite
- `validation_testing_demo.py` - Python code examples

## CLI Commands

### `pvcs test`

Run prompt test cases from a YAML file.

```bash
pvcs test <test_file> [OPTIONS]

Options:
  --project, -p PATH    Project root path
  --verbose, -v         Show detailed output
  --tag, -t TAG         Run only tests with this tag
```

### `pvcs validate`

Validate a prompt output against rules.

```bash
pvcs validate <prompt_id> <output> --config <config_file> [OPTIONS]

Options:
  --config, -c PATH     Validation config YAML file
  --project, -p PATH    Project root path
```

## API Reference

### Classes

- `PromptValidator`: Main validator class
- `ValidationRule`: Defines a single validation rule
- `ValidationType`: Enum of validation types
- `TestCase`: Represents a single test case
- `TestSuite`: Collection of test cases
- `PromptTestRunner`: Executes tests
- `TestReporter`: Formats and displays results

### Functions

- `create_validator_from_yaml(config)`: Create validator from YAML config
- `load_test_suite_from_yaml(path)`: Load test suite from YAML file
- `save_test_suite_to_yaml(suite, path)`: Save test suite to YAML file

## Troubleshooting

### JSON Schema validation not working

Make sure you have `jsonschema` installed:

```bash
pip install jsonschema
```

### Tests not finding prompts

Ensure your project root has either:
- `prompts.yaml` (single-file mode)
- `prompts/` directory (multi-file mode)

Use `--project` flag to specify the project root explicitly.

### Validation rules not matching

Check your regex patterns and string matching - they are case-sensitive by default.

## Contributing

Contributions are welcome! Please see the main README for contribution guidelines.
