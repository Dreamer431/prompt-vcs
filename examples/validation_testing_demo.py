"""
Example: Using the Prompt Validation and Testing Framework

This script demonstrates how to use the validation and testing features
of prompt-vcs to ensure your prompts work correctly.
"""

import sys
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from prompt_vcs import p, PromptValidator, ValidationRule, ValidationType
from prompt_vcs.testing import TestCase, TestSuite, PromptTestRunner, TestReporter


def example_1_basic_validation():
    """Example 1: Basic prompt validation"""
    print("\n" + "=" * 60)
    print("Example 1: Basic Prompt Validation")
    print("=" * 60)

    # Create a validator
    validator = PromptValidator()

    # Add validation rules
    validator.add_rule(ValidationRule(
        rule_type=ValidationType.LENGTH,
        name="reasonable_length",
        min_length=10,
        max_length=100,
    ))

    validator.add_rule(ValidationRule(
        rule_type=ValidationType.CONTAINS,
        name="has_name",
        substring="Alice",
    ))

    # Test some outputs
    test_outputs = [
        "Hello, Alice! Welcome to our system.",
        "Hi there!",  # Too short, missing "Alice"
        "Dear Alice, " + "x" * 100,  # Too long
    ]

    for i, output in enumerate(test_outputs, 1):
        print(f"\nTest {i}: {output[:50]}...")
        results = validator.validate(output)

        for result in results:
            status = "✓" if result.passed else "✗"
            print(f"  {status} {result.rule_name}", end="")
            if not result.passed:
                print(f" - {result.error_message}")
            else:
                print()


def example_2_regex_validation():
    """Example 2: Regex pattern validation"""
    print("\n" + "=" * 60)
    print("Example 2: Regex Pattern Validation")
    print("=" * 60)

    validator = PromptValidator()

    # Validate email format
    validator.add_rule(ValidationRule(
        rule_type=ValidationType.REGEX,
        name="contains_email",
        pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ))

    outputs = [
        "Contact us at support@example.com for help",
        "No email in this message",
    ]

    for output in outputs:
        print(f"\nOutput: {output}")
        results = validator.validate(output)
        if results[0].passed:
            print("  ✓ Valid email found")
        else:
            print("  ✗ No email found")


def example_3_custom_validation():
    """Example 3: Custom validation function"""
    print("\n" + "=" * 60)
    print("Example 3: Custom Validation Function")
    print("=" * 60)

    def has_polite_words(text: str) -> bool:
        """Check if text contains polite words."""
        polite_words = ["please", "thank you", "welcome", "欢迎", "谢谢"]
        return any(word in text.lower() for word in polite_words)

    validator = PromptValidator()
    validator.add_rule(ValidationRule(
        rule_type=ValidationType.CUSTOM,
        name="politeness_check",
        custom_validator=has_polite_words,
        error_message="Output should contain polite words",
    ))

    outputs = [
        "Welcome to our service!",
        "欢迎使用本系统",
        "You must do this now.",
    ]

    for output in outputs:
        print(f"\nOutput: {output}")
        if validator.validate_all(output):
            print("  ✓ Polite")
        else:
            print("  ✗ Not polite enough")


def example_4_test_case():
    """Example 4: Creating and running test cases"""
    print("\n" + "=" * 60)
    print("Example 4: Test Cases")
    print("=" * 60)

    # Note: This requires a prompts.yaml file to be set up
    # We'll create a simple test case structure

    test = TestCase(
        prompt_id="user_greeting",
        name="test_greeting_alice",
        inputs={"name": "Alice"},
        validation_config={
            "validation": [
                {"type": "contains", "substring": "Alice"},
                {"type": "length", "min_length": 5, "max_length": 100},
            ]
        },
    )

    print(f"Test Case: {test.name}")
    print(f"Prompt ID: {test.prompt_id}")
    print(f"Inputs: {test.inputs}")
    print(f"Validation Rules: {len(test.validator.rules)}")


def example_5_test_suite():
    """Example 5: Test suite organization"""
    print("\n" + "=" * 60)
    print("Example 5: Test Suite")
    print("=" * 60)

    # Create a test suite
    suite = TestSuite(
        name="Greeting Tests",
        description="Tests for all greeting prompts",
    )

    # Add multiple test cases
    suite.add_test(TestCase(
        prompt_id="user_greeting",
        name="test_alice",
        inputs={"name": "Alice"},
        tags=["smoke", "greeting"],
    ))

    suite.add_test(TestCase(
        prompt_id="user_greeting",
        name="test_bob",
        inputs={"name": "Bob"},
        tags=["greeting"],
    ))

    suite.add_test(TestCase(
        prompt_id="farewell",
        name="test_farewell",
        inputs={"name": "Charlie"},
        tags=["farewell"],
    ))

    print(f"Suite: {suite.name}")
    print(f"Total tests: {len(suite.test_cases)}")

    # Filter by tag
    smoke_tests = suite.get_tests_by_tag("smoke")
    print(f"Smoke tests: {len(smoke_tests)}")

    greeting_tests = suite.get_tests_by_prompt("user_greeting")
    print(f"Greeting tests: {len(greeting_tests)}")


def example_6_yaml_config():
    """Example 6: Loading validation from YAML"""
    print("\n" + "=" * 60)
    print("Example 6: YAML Configuration")
    print("=" * 60)

    # Example YAML config structure
    config = {
        "validation": [
            {
                "type": "length",
                "name": "reasonable_length",
                "min_length": 10,
                "max_length": 1000,
            },
            {
                "type": "contains",
                "name": "has_greeting",
                "substring": "Hello",
            },
            {
                "type": "regex",
                "name": "has_number",
                "pattern": r"\d+",
            },
        ]
    }

    from prompt_vcs.validator import create_validator_from_yaml

    validator = create_validator_from_yaml(config)
    print(f"Created validator with {len(validator.rules)} rules:")
    for rule in validator.rules:
        print(f"  - {rule.name} ({rule.rule_type.value})")


def main():
    """Run all examples"""
    print("\n" + "=" * 60)
    print("PROMPT-VCS VALIDATION & TESTING EXAMPLES")
    print("=" * 60)

    try:
        example_1_basic_validation()
        example_2_regex_validation()
        example_3_custom_validation()
        example_4_test_case()
        example_5_test_suite()
        example_6_yaml_config()

        print("\n" + "=" * 60)
        print("Examples completed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Create a prompts.yaml file in your project")
        print("2. Define validation rules in a YAML file")
        print("3. Create test suites for your prompts")
        print("4. Run tests with: pvcs test examples/test_suite.yaml")
        print("5. Validate outputs with: pvcs validate <prompt_id> <output> --config validation.yaml")

    except Exception as e:
        print(f"\nError running examples: {e}")
        print("Make sure you have prompt-vcs installed and configured.")


if __name__ == "__main__":
    main()
