"""
Prompt testing framework: define and run test cases for prompts.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from prompt_vcs.manager import get_manager
from prompt_vcs.validator import PromptValidator, create_validator_from_yaml


class TestStatus(str, Enum):
    """Status of a test case execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestCase:
    """
    Represents a single test case for a prompt.

    A test case includes:
    - The prompt ID to test
    - Input variables for the prompt
    - Expected output patterns or validation rules
    - Optional description and metadata
    """

    prompt_id: str
    name: str
    inputs: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    # Validation rules (can be defined inline or reference a validator)
    validator: Optional[PromptValidator] = None
    validation_config: Optional[dict] = None

    # Expected output for exact matching (alternative to validator)
    expected_output: Optional[str] = None

    # Test metadata
    skip: bool = False
    skip_reason: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize validator from config if provided."""
        if self.validation_config and not self.validator:
            self.validator = create_validator_from_yaml(self.validation_config)


@dataclass
class TestResult:
    """Result of running a single test case."""

    test_name: str
    prompt_id: str
    status: TestStatus

    # Rendered prompt and output
    rendered_prompt: str = ""

    # Validation results
    validation_results: list[Any] = field(default_factory=list)

    # Error information
    error_message: Optional[str] = None
    error_details: Optional[dict] = None

    # Timing information
    duration_ms: float = 0.0


@dataclass
class TestSuite:
    """
    A collection of test cases for prompts.

    Test suites can be loaded from YAML files and executed together.
    """

    name: str
    description: str = ""
    test_cases: list[TestCase] = field(default_factory=list)

    def add_test(self, test_case: TestCase) -> None:
        """Add a test case to the suite."""
        self.test_cases.append(test_case)

    def get_tests_by_tag(self, tag: str) -> list[TestCase]:
        """Get all test cases with a specific tag."""
        return [tc for tc in self.test_cases if tag in tc.tags]

    def get_tests_by_prompt(self, prompt_id: str) -> list[TestCase]:
        """Get all test cases for a specific prompt."""
        return [tc for tc in self.test_cases if tc.prompt_id == prompt_id]


class PromptTestRunner:
    """
    Runs test cases and test suites for prompts.

    Example:
        runner = PromptTestRunner()

        # Create a test case
        test = TestCase(
            prompt_id="user_greeting",
            name="test_greeting_with_name",
            inputs={"name": "Alice"},
            validation_config={
                "validation": [
                    {"type": "contains", "substring": "Alice"},
                    {"type": "length", "min_length": 5, "max_length": 100},
                ]
            }
        )

        # Run the test
        result = runner.run_test(test)
        print(f"Test {result.status}: {result.test_name}")
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the test runner.

        Args:
            project_root: Optional project root path for prompt resolution
        """
        self.manager = get_manager()
        if project_root:
            self.manager.set_project_root(project_root)

    def run_test(self, test_case: TestCase) -> TestResult:
        """
        Run a single test case.

        Args:
            test_case: The test case to run

        Returns:
            Test result with status and details
        """
        import time

        start_time = time.time()

        # Check if test should be skipped
        if test_case.skip:
            return TestResult(
                test_name=test_case.name,
                prompt_id=test_case.prompt_id,
                status=TestStatus.SKIPPED,
                error_message=test_case.skip_reason,
            )

        try:
            # Render the prompt with inputs
            rendered = self.manager.get_prompt(
                test_case.prompt_id,
                **test_case.inputs
            )

            # Determine test status
            status = TestStatus.PASSED
            validation_results = []
            error_message = None

            # Check expected output if provided
            if test_case.expected_output is not None:
                if rendered != test_case.expected_output:
                    status = TestStatus.FAILED
                    error_message = "Output does not match expected value"

            # Run validation rules if provided
            if test_case.validator:
                validation_results = test_case.validator.validate(rendered)

                # Check if any validation failed
                if not all(vr.passed for vr in validation_results):
                    status = TestStatus.FAILED
                    failed_rules = [vr for vr in validation_results if not vr.passed]
                    error_message = f"{len(failed_rules)} validation rule(s) failed"

            duration_ms = (time.time() - start_time) * 1000

            return TestResult(
                test_name=test_case.name,
                prompt_id=test_case.prompt_id,
                status=status,
                rendered_prompt=rendered,
                validation_results=validation_results,
                error_message=error_message,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            return TestResult(
                test_name=test_case.name,
                prompt_id=test_case.prompt_id,
                status=TestStatus.ERROR,
                error_message=str(e),
                error_details={"exception_type": type(e).__name__},
                duration_ms=duration_ms,
            )

    def run_suite(self, test_suite: TestSuite) -> list[TestResult]:
        """
        Run all test cases in a test suite.

        Args:
            test_suite: The test suite to run

        Returns:
            List of test results
        """
        results = []

        for test_case in test_suite.test_cases:
            result = self.run_test(test_case)
            results.append(result)

        return results

    def run_tests_by_tag(self, test_suite: TestSuite, tag: str) -> list[TestResult]:
        """
        Run only test cases with a specific tag.

        Args:
            test_suite: The test suite containing tests
            tag: Tag to filter by

        Returns:
            List of test results
        """
        filtered_tests = test_suite.get_tests_by_tag(tag)
        results = []

        for test_case in filtered_tests:
            result = self.run_test(test_case)
            results.append(result)

        return results


def load_test_suite_from_yaml(path: Path) -> TestSuite:
    """
    Load a test suite from a YAML file.

    Expected format:
        name: "User Greeting Tests"
        description: "Tests for user greeting prompts"
        tests:
          - prompt_id: "user_greeting"
            name: "test_greeting_with_name"
            inputs:
              name: "Alice"
            validation:
              - type: "contains"
                substring: "Alice"
              - type: "length"
                min_length: 5
                max_length: 100

          - prompt_id: "farewell"
            name: "test_farewell"
            inputs:
              name: "Bob"
            expected_output: "再见，Bob！期待再次见到你。"

    Args:
        path: Path to the YAML file

    Returns:
        Loaded TestSuite instance

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the YAML format is invalid
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid test suite format in {path}: expected a dictionary")

    suite_name = data.get("name", path.stem)
    suite_description = data.get("description", "")

    test_suite = TestSuite(name=suite_name, description=suite_description)

    tests_data = data.get("tests", [])
    if not isinstance(tests_data, list):
        raise ValueError("'tests' must be a list of test case dictionaries")

    for test_dict in tests_data:
        if not isinstance(test_dict, dict):
            raise ValueError("Each test case must be a dictionary")

        # Required fields
        prompt_id = test_dict.get("prompt_id")
        if not prompt_id:
            raise ValueError("Each test case must have a 'prompt_id' field")

        name = test_dict.get("name")
        if not name:
            raise ValueError("Each test case must have a 'name' field")

        # Optional fields
        inputs = test_dict.get("inputs", {})
        description = test_dict.get("description", "")
        expected_output = test_dict.get("expected_output")
        skip = test_dict.get("skip", False)
        skip_reason = test_dict.get("skip_reason", "")
        tags = test_dict.get("tags", [])

        # Validation config
        validation_config = None
        if "validation" in test_dict:
            validation_config = {"validation": test_dict["validation"]}

        test_case = TestCase(
            prompt_id=prompt_id,
            name=name,
            inputs=inputs,
            description=description,
            validation_config=validation_config,
            expected_output=expected_output,
            skip=skip,
            skip_reason=skip_reason,
            tags=tags,
        )

        test_suite.add_test(test_case)

    return test_suite


def save_test_suite_to_yaml(test_suite: TestSuite, path: Path) -> None:
    """
    Save a test suite to a YAML file.

    Args:
        test_suite: The test suite to save
        path: Path to save the YAML file
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "name": test_suite.name,
        "description": test_suite.description,
        "tests": [],
    }

    for test_case in test_suite.test_cases:
        test_dict = {
            "prompt_id": test_case.prompt_id,
            "name": test_case.name,
        }

        if test_case.inputs:
            test_dict["inputs"] = test_case.inputs

        if test_case.description:
            test_dict["description"] = test_case.description

        if test_case.expected_output is not None:
            test_dict["expected_output"] = test_case.expected_output

        if test_case.validation_config:
            test_dict["validation"] = test_case.validation_config.get("validation", [])

        if test_case.skip:
            test_dict["skip"] = True
            if test_case.skip_reason:
                test_dict["skip_reason"] = test_case.skip_reason

        if test_case.tags:
            test_dict["tags"] = test_case.tags

        data["tests"].append(test_dict)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class TestReporter:
    """Formats and displays test results."""

    @staticmethod
    def _safe_print(text: str) -> None:
        """
        Safely print text, handling Unicode encoding issues on Windows.

        Args:
            text: Text to print
        """
        try:
            print(text)
        except UnicodeEncodeError:
            # Fallback for Windows console without UTF-8 support
            import sys
            if sys.platform == "win32":
                # Replace Unicode symbols with ASCII alternatives
                text = text.replace("✓", "+").replace("✗", "x").replace("⚠", "!").replace("-", "-")
            print(text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))

    @staticmethod
    def print_summary(results: list[TestResult]) -> None:
        """
        Print a summary of test results.

        Args:
            results: List of test results to summarize
        """
        total = len(results)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in results if r.status == TestStatus.ERROR)

        TestReporter._safe_print("\n" + "=" * 60)
        TestReporter._safe_print("TEST SUMMARY")
        TestReporter._safe_print("=" * 60)
        TestReporter._safe_print(f"Total:   {total}")
        TestReporter._safe_print(f"Passed:  {passed} +")
        TestReporter._safe_print(f"Failed:  {failed} x")
        TestReporter._safe_print(f"Skipped: {skipped} -")
        TestReporter._safe_print(f"Errors:  {errors} !")
        TestReporter._safe_print("=" * 60)

        if total > 0:
            pass_rate = (passed / total) * 100
            TestReporter._safe_print(f"Pass Rate: {pass_rate:.1f}%")

        TestReporter._safe_print("")

    @staticmethod
    def print_detailed(results: list[TestResult], verbose: bool = False) -> None:
        """
        Print detailed test results.

        Args:
            results: List of test results to display
            verbose: If True, show full output and validation details
        """
        for result in results:
            status_symbol = {
                TestStatus.PASSED: "+",
                TestStatus.FAILED: "x",
                TestStatus.SKIPPED: "-",
                TestStatus.ERROR: "!",
            }.get(result.status, "?")

            TestReporter._safe_print(f"\n{status_symbol} {result.test_name} [{result.prompt_id}]")
            TestReporter._safe_print(f"  Status: {result.status.value}")
            TestReporter._safe_print(f"  Duration: {result.duration_ms:.2f}ms")

            if result.error_message:
                TestReporter._safe_print(f"  Error: {result.error_message}")

            if verbose:
                if result.rendered_prompt:
                    TestReporter._safe_print("\n  Rendered Output:")
                    TestReporter._safe_print("  " + "-" * 50)
                    for line in result.rendered_prompt.split("\n"):
                        TestReporter._safe_print(f"  {line}")
                    TestReporter._safe_print("  " + "-" * 50)

                if result.validation_results:
                    TestReporter._safe_print("\n  Validation Results:")
                    for vr in result.validation_results:
                        vr_symbol = "+" if vr.passed else "x"
                        TestReporter._safe_print(f"    {vr_symbol} {vr.rule_name}")
                        if not vr.passed and vr.error_message:
                            TestReporter._safe_print(f"      {vr.error_message}")