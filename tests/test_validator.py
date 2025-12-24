"""
Tests for the validator module.
"""

import pytest

from prompt_vcs.validator import (
    PromptValidator,
    ValidationRule,
    ValidationType,
    ValidationResult,
    create_validator_from_yaml,
)


class TestValidationRule:
    """Test ValidationRule dataclass."""

    def test_json_schema_rule_without_jsonschema(self, monkeypatch):
        """Test that JSON_SCHEMA rule raises error when jsonschema is not installed."""
        # Mock HAS_JSONSCHEMA to False
        import prompt_vcs.validator as validator_module
        monkeypatch.setattr(validator_module, "HAS_JSONSCHEMA", False)

        with pytest.raises(ImportError, match="jsonschema package is required"):
            ValidationRule(
                rule_type=ValidationType.JSON_SCHEMA,
                schema={"type": "string"},
            )

    def test_regex_rule_requires_pattern(self):
        """Test that REGEX rule requires pattern parameter."""
        with pytest.raises(ValueError, match="REGEX validation requires 'pattern'"):
            ValidationRule(rule_type=ValidationType.REGEX)

    def test_regex_rule_validates_pattern(self):
        """Test that REGEX rule validates pattern syntax."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            ValidationRule(
                rule_type=ValidationType.REGEX,
                pattern="[invalid(regex",
            )

    def test_length_rule_requires_min_or_max(self):
        """Test that LENGTH rule requires at least one of min/max."""
        with pytest.raises(ValueError, match="LENGTH validation requires"):
            ValidationRule(rule_type=ValidationType.LENGTH)

    def test_contains_rule_requires_substring(self):
        """Test that CONTAINS rule requires substring parameter."""
        with pytest.raises(ValueError, match="CONTAINS validation requires 'substring'"):
            ValidationRule(rule_type=ValidationType.CONTAINS)

    def test_custom_rule_requires_validator(self):
        """Test that CUSTOM rule requires custom_validator parameter."""
        with pytest.raises(ValueError, match="CUSTOM validation requires 'custom_validator'"):
            ValidationRule(rule_type=ValidationType.CUSTOM)


class TestPromptValidator:
    """Test PromptValidator class."""

    def test_add_and_clear_rules(self):
        """Test adding and clearing validation rules."""
        validator = PromptValidator()
        assert len(validator.rules) == 0

        rule = ValidationRule(
            rule_type=ValidationType.LENGTH,
            min_length=5,
        )
        validator.add_rule(rule)
        assert len(validator.rules) == 1

        validator.clear_rules()
        assert len(validator.rules) == 0

    def test_validate_length_min(self):
        """Test length validation with minimum."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.LENGTH,
            name="min_length",
            min_length=10,
        ))

        # Test passing case
        results = validator.validate("This is a long enough string")
        assert len(results) == 1
        assert results[0].passed is True

        # Test failing case
        results = validator.validate("Short")
        assert len(results) == 1
        assert results[0].passed is False
        assert "too short" in results[0].error_message.lower()

    def test_validate_length_max(self):
        """Test length validation with maximum."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.LENGTH,
            name="max_length",
            max_length=10,
        ))

        # Test passing case
        results = validator.validate("Short")
        assert len(results) == 1
        assert results[0].passed is True

        # Test failing case
        results = validator.validate("This is way too long for the limit")
        assert len(results) == 1
        assert results[0].passed is False
        assert "too long" in results[0].error_message.lower()

    def test_validate_regex_match(self):
        """Test regex validation."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.REGEX,
            name="email_pattern",
            pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        ))

        # Test passing case
        results = validator.validate("Contact us at test@example.com for help")
        assert len(results) == 1
        assert results[0].passed is True

        # Test failing case
        results = validator.validate("No email here")
        assert len(results) == 1
        assert results[0].passed is False

    def test_validate_contains(self):
        """Test contains validation."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.CONTAINS,
            name="has_keyword",
            substring="important",
        ))

        # Test passing case
        results = validator.validate("This is an important message")
        assert len(results) == 1
        assert results[0].passed is True

        # Test failing case
        results = validator.validate("This is a regular message")
        assert len(results) == 1
        assert results[0].passed is False

    def test_validate_custom(self):
        """Test custom validation function."""
        def is_uppercase(text: str) -> bool:
            return text.isupper()

        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.CUSTOM,
            name="uppercase",
            custom_validator=is_uppercase,
        ))

        # Test passing case
        results = validator.validate("HELLO WORLD")
        assert len(results) == 1
        assert results[0].passed is True

        # Test failing case
        results = validator.validate("Hello World")
        assert len(results) == 1
        assert results[0].passed is False

    def test_validate_custom_with_exception(self):
        """Test custom validator that raises exception."""
        def bad_validator(text: str) -> bool:
            raise RuntimeError("Something went wrong")

        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.CUSTOM,
            name="bad",
            custom_validator=bad_validator,
        ))

        results = validator.validate("Test")
        assert len(results) == 1
        assert results[0].passed is False
        assert "exception" in results[0].error_message.lower()

    def test_validate_all(self):
        """Test validate_all method."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.LENGTH,
            min_length=5,
            max_length=30,
        ))
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.CONTAINS,
            substring="test",
        ))

        # All rules pass
        assert validator.validate_all("This is a test string") is True

        # One rule fails
        assert validator.validate_all("This is too long to pass the maximum length rule") is False

    def test_multiple_rules(self):
        """Test validator with multiple rules."""
        validator = PromptValidator()
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.LENGTH,
            name="length",
            min_length=10,
            max_length=100,
        ))
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.CONTAINS,
            name="contains_hello",
            substring="hello",
        ))
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.REGEX,
            name="has_number",
            pattern=r"\d+",
        ))

        # All rules pass
        results = validator.validate("hello world with number 42")
        assert len(results) == 3
        assert all(r.passed for r in results)

        # Some rules fail
        results = validator.validate("short")
        assert len(results) == 3
        assert sum(1 for r in results if r.passed) < 3


class TestCreateValidatorFromYaml:
    """Test create_validator_from_yaml function."""

    def test_create_validator_from_yaml(self):
        """Test creating validator from YAML config."""
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
                    "substring": "hello",
                },
            ]
        }

        validator = create_validator_from_yaml(config)
        assert len(validator.rules) == 2
        assert validator.rules[0].name == "reasonable_length"
        assert validator.rules[1].name == "has_greeting"

    def test_create_validator_invalid_config(self):
        """Test error handling for invalid config."""
        # validation is not a list
        with pytest.raises(ValueError, match="must be a list"):
            create_validator_from_yaml({"validation": "not a list"})

        # Rule without type
        with pytest.raises(ValueError, match="must have a 'type'"):
            create_validator_from_yaml({"validation": [{"name": "test"}]})

        # Unknown validation type
        with pytest.raises(ValueError, match="Unknown validation type"):
            create_validator_from_yaml({"validation": [{"type": "unknown"}]})

    def test_create_validator_with_all_types(self):
        """Test creating validator with all validation types."""
        config = {
            "validation": [
                {
                    "type": "length",
                    "min_length": 5,
                },
                {
                    "type": "regex",
                    "pattern": r"\d+",
                },
                {
                    "type": "contains",
                    "substring": "test",
                },
            ]
        }

        validator = create_validator_from_yaml(config)
        assert len(validator.rules) == 3
        assert validator.rules[0].rule_type == ValidationType.LENGTH
        assert validator.rules[1].rule_type == ValidationType.REGEX
        assert validator.rules[2].rule_type == ValidationType.CONTAINS


# Only test JSON schema if jsonschema is available
try:
    import jsonschema

    class TestJsonSchemaValidation:
        """Test JSON schema validation (requires jsonschema package)."""

        def test_validate_json_schema_valid(self):
            """Test JSON schema validation with valid JSON."""
            validator = PromptValidator()
            validator.add_rule(ValidationRule(
                rule_type=ValidationType.JSON_SCHEMA,
                name="user_schema",
                schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "number"},
                    },
                    "required": ["name"],
                },
            ))

            # Valid JSON
            results = validator.validate('{"name": "Alice", "age": 30}')
            assert len(results) == 1
            assert results[0].passed is True

        def test_validate_json_schema_invalid_json(self):
            """Test JSON schema validation with invalid JSON."""
            validator = PromptValidator()
            validator.add_rule(ValidationRule(
                rule_type=ValidationType.JSON_SCHEMA,
                schema={"type": "object"},
            ))

            # Invalid JSON syntax
            results = validator.validate("not valid json")
            assert len(results) == 1
            assert results[0].passed is False
            assert "Invalid JSON" in results[0].error_message

        def test_validate_json_schema_fails(self):
            """Test JSON schema validation failure."""
            validator = PromptValidator()
            validator.add_rule(ValidationRule(
                rule_type=ValidationType.JSON_SCHEMA,
                schema={
                    "type": "object",
                    "properties": {
                        "age": {"type": "number"},
                    },
                },
            ))

            # Valid JSON but doesn't match schema (age is string, not number)
            results = validator.validate('{"age": "thirty"}')
            assert len(results) == 1
            assert results[0].passed is False
            assert "Schema validation failed" in results[0].error_message

except ImportError:
    pass