"""
Prompt validation module: validates prompt schemas and outputs.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class ValidationType(str, Enum):
    """Types of validation that can be performed."""
    JSON_SCHEMA = "json_schema"
    REGEX = "regex"
    LENGTH = "length"
    CONTAINS = "contains"
    CUSTOM = "custom"


@dataclass
class ValidationRule:
    """Represents a single validation rule for a prompt."""

    rule_type: ValidationType
    name: str = ""
    description: str = ""

    # Type-specific parameters
    schema: Optional[dict] = None  # For JSON_SCHEMA
    pattern: Optional[str] = None  # For REGEX
    min_length: Optional[int] = None  # For LENGTH
    max_length: Optional[int] = None  # For LENGTH
    substring: Optional[str] = None  # For CONTAINS
    custom_validator: Optional[Callable[[str], bool]] = None  # For CUSTOM

    # Error message customization
    error_message: Optional[str] = None

    def __post_init__(self):
        """Validate rule configuration."""
        if self.rule_type == ValidationType.JSON_SCHEMA:
            if not HAS_JSONSCHEMA:
                raise ImportError(
                    "jsonschema package is required for JSON_SCHEMA validation. "
                    "Install it with: pip install jsonschema"
                )
            if self.schema is None:
                raise ValueError("JSON_SCHEMA validation requires 'schema' parameter")

        elif self.rule_type == ValidationType.REGEX:
            if self.pattern is None:
                raise ValueError("REGEX validation requires 'pattern' parameter")
            # Compile pattern to validate it
            try:
                re.compile(self.pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")

        elif self.rule_type == ValidationType.LENGTH:
            if self.min_length is None and self.max_length is None:
                raise ValueError("LENGTH validation requires at least one of 'min_length' or 'max_length'")

        elif self.rule_type == ValidationType.CONTAINS:
            if self.substring is None:
                raise ValueError("CONTAINS validation requires 'substring' parameter")

        elif self.rule_type == ValidationType.CUSTOM:
            if self.custom_validator is None:
                raise ValueError("CUSTOM validation requires 'custom_validator' parameter")


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    rule_name: str
    error_message: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class PromptValidator:
    """
    Validates prompt outputs against defined schemas and rules.

    Example:
        validator = PromptValidator()

        # Add JSON schema validation
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.JSON_SCHEMA,
            name="valid_json",
            schema={"type": "object", "properties": {"name": {"type": "string"}}},
        ))

        # Add length validation
        validator.add_rule(ValidationRule(
            rule_type=ValidationType.LENGTH,
            name="reasonable_length",
            min_length=10,
            max_length=1000,
        ))

        # Validate a prompt output
        results = validator.validate("Your prompt output here")
    """

    def __init__(self):
        """Initialize the validator with an empty rule set."""
        self.rules: list[ValidationRule] = []

    def add_rule(self, rule: ValidationRule) -> None:
        """
        Add a validation rule.

        Args:
            rule: The validation rule to add
        """
        self.rules.append(rule)

    def clear_rules(self) -> None:
        """Remove all validation rules."""
        self.rules.clear()

    def validate(self, output: str) -> list[ValidationResult]:
        """
        Validate a prompt output against all rules.

        Args:
            output: The prompt output to validate

        Returns:
            List of validation results, one per rule
        """
        results = []

        for rule in self.rules:
            result = self._validate_rule(output, rule)
            results.append(result)

        return results

    def validate_all(self, output: str) -> bool:
        """
        Check if output passes all validation rules.

        Args:
            output: The prompt output to validate

        Returns:
            True if all rules pass, False otherwise
        """
        results = self.validate(output)
        return all(r.passed for r in results)

    def _validate_rule(self, output: str, rule: ValidationRule) -> ValidationResult:
        """
        Validate output against a single rule.

        Args:
            output: The prompt output to validate
            rule: The validation rule to check

        Returns:
            Validation result
        """
        try:
            if rule.rule_type == ValidationType.JSON_SCHEMA:
                return self._validate_json_schema(output, rule)
            elif rule.rule_type == ValidationType.REGEX:
                return self._validate_regex(output, rule)
            elif rule.rule_type == ValidationType.LENGTH:
                return self._validate_length(output, rule)
            elif rule.rule_type == ValidationType.CONTAINS:
                return self._validate_contains(output, rule)
            elif rule.rule_type == ValidationType.CUSTOM:
                return self._validate_custom(output, rule)
            else:
                return ValidationResult(
                    passed=False,
                    rule_name=rule.name,
                    error_message=f"Unknown validation type: {rule.rule_type}",
                )
        except Exception as e:
            return ValidationResult(
                passed=False,
                rule_name=rule.name,
                error_message=f"Validation error: {str(e)}",
                details={"exception": str(e)},
            )

    def _validate_json_schema(self, output: str, rule: ValidationRule) -> ValidationResult:
        """Validate output against a JSON schema."""
        import json

        try:
            # Parse output as JSON
            parsed = json.loads(output)

            # Validate against schema
            jsonschema.validate(instance=parsed, schema=rule.schema)

            return ValidationResult(
                passed=True,
                rule_name=rule.name or "json_schema",
            )
        except json.JSONDecodeError as e:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "json_schema",
                error_message=rule.error_message or f"Invalid JSON: {str(e)}",
                details={"json_error": str(e)},
            )
        except jsonschema.ValidationError as e:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "json_schema",
                error_message=rule.error_message or f"Schema validation failed: {e.message}",
                details={
                    "schema_path": list(e.schema_path),
                    "instance_path": list(e.absolute_path),
                    "validator": e.validator,
                },
            )

    def _validate_regex(self, output: str, rule: ValidationRule) -> ValidationResult:
        """Validate output against a regex pattern."""
        pattern = re.compile(rule.pattern)
        match = pattern.search(output)

        if match:
            return ValidationResult(
                passed=True,
                rule_name=rule.name or "regex",
                details={"matched": match.group(0)},
            )
        else:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "regex",
                error_message=rule.error_message or f"Output does not match pattern: {rule.pattern}",
            )

    def _validate_length(self, output: str, rule: ValidationRule) -> ValidationResult:
        """Validate output length."""
        length = len(output)

        if rule.min_length is not None and length < rule.min_length:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "length",
                error_message=rule.error_message or f"Output too short: {length} < {rule.min_length}",
                details={"length": length, "min": rule.min_length},
            )

        if rule.max_length is not None and length > rule.max_length:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "length",
                error_message=rule.error_message or f"Output too long: {length} > {rule.max_length}",
                details={"length": length, "max": rule.max_length},
            )

        return ValidationResult(
            passed=True,
            rule_name=rule.name or "length",
            details={"length": length},
        )

    def _validate_contains(self, output: str, rule: ValidationRule) -> ValidationResult:
        """Validate that output contains a substring."""
        if rule.substring in output:
            return ValidationResult(
                passed=True,
                rule_name=rule.name or "contains",
            )
        else:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "contains",
                error_message=rule.error_message or f"Output does not contain: {rule.substring}",
            )

    def _validate_custom(self, output: str, rule: ValidationRule) -> ValidationResult:
        """Validate output using a custom validator function."""
        try:
            passed = rule.custom_validator(output)

            if passed:
                return ValidationResult(
                    passed=True,
                    rule_name=rule.name or "custom",
                )
            else:
                return ValidationResult(
                    passed=False,
                    rule_name=rule.name or "custom",
                    error_message=rule.error_message or "Custom validation failed",
                )
        except Exception as e:
            return ValidationResult(
                passed=False,
                rule_name=rule.name or "custom",
                error_message=f"Custom validator raised exception: {str(e)}",
                details={"exception": str(e)},
            )


def create_validator_from_yaml(config: dict) -> PromptValidator:
    """
    Create a validator from a YAML configuration.

    Expected format:
        validation:
          - type: json_schema
            name: "valid_json"
            schema:
              type: object
              properties:
                name:
                  type: string
          - type: length
            name: "reasonable_length"
            min_length: 10
            max_length: 1000
          - type: regex
            name: "contains_email"
            pattern: "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"

    Args:
        config: Dictionary containing validation rules

    Returns:
        Configured PromptValidator instance
    """
    validator = PromptValidator()

    rules_config = config.get("validation", [])
    if not isinstance(rules_config, list):
        raise ValueError("'validation' must be a list of rule dictionaries")

    for rule_dict in rules_config:
        rule_type_str = rule_dict.get("type")
        if not rule_type_str:
            raise ValueError("Each validation rule must have a 'type' field")

        try:
            rule_type = ValidationType(rule_type_str)
        except ValueError:
            raise ValueError(f"Unknown validation type: {rule_type_str}")

        # Build rule based on type
        rule_kwargs = {
            "rule_type": rule_type,
            "name": rule_dict.get("name", ""),
            "description": rule_dict.get("description", ""),
            "error_message": rule_dict.get("error_message"),
        }

        if rule_type == ValidationType.JSON_SCHEMA:
            rule_kwargs["schema"] = rule_dict.get("schema")
        elif rule_type == ValidationType.REGEX:
            rule_kwargs["pattern"] = rule_dict.get("pattern")
        elif rule_type == ValidationType.LENGTH:
            rule_kwargs["min_length"] = rule_dict.get("min_length")
            rule_kwargs["max_length"] = rule_dict.get("max_length")
        elif rule_type == ValidationType.CONTAINS:
            rule_kwargs["substring"] = rule_dict.get("substring")

        rule = ValidationRule(**rule_kwargs)
        validator.add_rule(rule)

    return validator