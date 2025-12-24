"""
Tests for the testing module.
"""

import tempfile
from pathlib import Path

import pytest

from prompt_vcs.testing import (
    TestCase,
    TestSuite,
    TestStatus,
    PromptTestRunner,
    TestReporter,
    load_test_suite_from_yaml,
    save_test_suite_to_yaml,
)
from prompt_vcs.validator import ValidationRule, ValidationType


# Note: auto_reset_manager fixture is defined in conftest.py with autouse=True


class TestTestCase:
    """Test TestCase dataclass."""

    def test_create_test_case(self):
        """Test creating a basic test case."""
        test = TestCase(
            prompt_id="greeting",
            name="test_greeting",
            inputs={"name": "Alice"},
            description="Test greeting prompt",
        )

        assert test.prompt_id == "greeting"
        assert test.name == "test_greeting"
        assert test.inputs == {"name": "Alice"}
        assert test.description == "Test greeting prompt"
        assert test.skip is False

    def test_test_case_with_validation_config(self):
        """Test test case with validation config."""
        test = TestCase(
            prompt_id="greeting",
            name="test_greeting",
            validation_config={
                "validation": [
                    {"type": "length", "min_length": 5},
                ]
            },
        )

        # Validator should be created from config
        assert test.validator is not None
        assert len(test.validator.rules) == 1

    def test_test_case_skip(self):
        """Test skipped test case."""
        test = TestCase(
            prompt_id="greeting",
            name="test_skip",
            skip=True,
            skip_reason="Not implemented yet",
        )

        assert test.skip is True
        assert test.skip_reason == "Not implemented yet"


class TestTestSuite:
    """Test TestSuite class."""

    def test_create_test_suite(self):
        """Test creating a test suite."""
        suite = TestSuite(
            name="Greeting Tests",
            description="Tests for greeting prompts",
        )

        assert suite.name == "Greeting Tests"
        assert suite.description == "Tests for greeting prompts"
        assert len(suite.test_cases) == 0

    def test_add_test(self):
        """Test adding test cases to suite."""
        suite = TestSuite(name="Tests")

        test1 = TestCase(prompt_id="p1", name="test1")
        test2 = TestCase(prompt_id="p2", name="test2")

        suite.add_test(test1)
        suite.add_test(test2)

        assert len(suite.test_cases) == 2

    def test_get_tests_by_tag(self):
        """Test filtering tests by tag."""
        suite = TestSuite(name="Tests")

        test1 = TestCase(prompt_id="p1", name="test1", tags=["smoke", "quick"])
        test2 = TestCase(prompt_id="p2", name="test2", tags=["integration"])
        test3 = TestCase(prompt_id="p3", name="test3", tags=["smoke"])

        suite.add_test(test1)
        suite.add_test(test2)
        suite.add_test(test3)

        smoke_tests = suite.get_tests_by_tag("smoke")
        assert len(smoke_tests) == 2
        assert all("smoke" in t.tags for t in smoke_tests)

    def test_get_tests_by_prompt(self):
        """Test filtering tests by prompt ID."""
        suite = TestSuite(name="Tests")

        test1 = TestCase(prompt_id="greeting", name="test1")
        test2 = TestCase(prompt_id="farewell", name="test2")
        test3 = TestCase(prompt_id="greeting", name="test3")

        suite.add_test(test1)
        suite.add_test(test2)
        suite.add_test(test3)

        greeting_tests = suite.get_tests_by_prompt("greeting")
        assert len(greeting_tests) == 2
        assert all(t.prompt_id == "greeting" for t in greeting_tests)


class TestPromptTestRunner:
    """Test PromptTestRunner class."""

    def test_run_test_with_expected_output(self, tmp_path):
        """Test running a test with expected output."""
        # Setup test environment
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        # Create prompts.yaml
        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hello, {name}!",
                "description": "Greeting",
            }
        })

        # Create test case
        test = TestCase(
            prompt_id="greeting",
            name="test_greeting_alice",
            inputs={"name": "Alice"},
            expected_output="Hello, Alice!",
        )

        # Run test
        runner = PromptTestRunner(project_root=tmp_path)
        result = runner.run_test(test)

        assert result.status == TestStatus.PASSED
        assert result.rendered_prompt == "Hello, Alice!"

    def test_run_test_with_expected_output_fail(self, tmp_path):
        """Test running a test that fails expected output check."""
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hello, {name}!",
                "description": "Greeting",
            }
        })

        # Test with wrong expected output
        test = TestCase(
            prompt_id="greeting",
            name="test_greeting_fail",
            inputs={"name": "Alice"},
            expected_output="Hi, Alice!",  # Wrong!
        )

        runner = PromptTestRunner(project_root=tmp_path)
        result = runner.run_test(test)

        assert result.status == TestStatus.FAILED
        assert "does not match expected" in result.error_message

    def test_run_test_with_validation(self, tmp_path):
        """Test running a test with validation rules."""
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hello, {name}!",
                "description": "Greeting",
            }
        })

        # Test with validation
        test = TestCase(
            prompt_id="greeting",
            name="test_with_validation",
            inputs={"name": "Alice"},
            validation_config={
                "validation": [
                    {"type": "contains", "substring": "Alice"},
                    {"type": "length", "min_length": 5, "max_length": 20},
                ]
            },
        )

        runner = PromptTestRunner(project_root=tmp_path)
        result = runner.run_test(test)

        assert result.status == TestStatus.PASSED
        assert len(result.validation_results) == 2
        assert all(vr.passed for vr in result.validation_results)

    def test_run_test_validation_failure(self, tmp_path):
        """Test running a test that fails validation."""
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hi!",
                "description": "Short greeting",
            }
        })

        # Test with validation that will fail
        test = TestCase(
            prompt_id="greeting",
            name="test_validation_fail",
            validation_config={
                "validation": [
                    {"type": "length", "min_length": 10},  # Will fail
                ]
            },
        )

        runner = PromptTestRunner(project_root=tmp_path)
        result = runner.run_test(test)

        assert result.status == TestStatus.FAILED
        assert "validation rule(s) failed" in result.error_message

    def test_run_test_skip(self):
        """Test running a skipped test."""
        test = TestCase(
            prompt_id="greeting",
            name="test_skip",
            skip=True,
            skip_reason="Not ready",
        )

        runner = PromptTestRunner()
        result = runner.run_test(test)

        assert result.status == TestStatus.SKIPPED
        assert result.error_message == "Not ready"

    def test_run_test_error(self, tmp_path):
        """Test running a test that encounters an error."""
        from prompt_vcs.manager import get_manager

        manager = get_manager()
        manager.set_project_root(tmp_path)

        # Test for non-existent prompt
        test = TestCase(
            prompt_id="nonexistent",
            name="test_error",
        )

        runner = PromptTestRunner(project_root=tmp_path)
        result = runner.run_test(test)

        assert result.status == TestStatus.ERROR
        assert result.error_message is not None

    def test_run_suite(self, tmp_path):
        """Test running a complete test suite."""
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hello, {name}!",
                "description": "Greeting",
            },
            "farewell": {
                "template": "Goodbye, {name}!",
                "description": "Farewell",
            }
        })

        # Create suite
        suite = TestSuite(name="All Tests")
        suite.add_test(TestCase(
            prompt_id="greeting",
            name="test1",
            inputs={"name": "Alice"},
            expected_output="Hello, Alice!",
        ))
        suite.add_test(TestCase(
            prompt_id="farewell",
            name="test2",
            inputs={"name": "Bob"},
            expected_output="Goodbye, Bob!",
        ))

        runner = PromptTestRunner(project_root=tmp_path)
        results = runner.run_suite(suite)

        assert len(results) == 2
        assert all(r.status == TestStatus.PASSED for r in results)

    def test_run_tests_by_tag(self, tmp_path):
        """Test running tests filtered by tag."""
        from prompt_vcs.manager import get_manager
        from prompt_vcs.templates import save_prompts_file

        manager = get_manager()
        manager.set_project_root(tmp_path)

        prompts_file = tmp_path / "prompts.yaml"
        save_prompts_file(prompts_file, {
            "greeting": {
                "template": "Hello!",
                "description": "Greeting",
            }
        })

        suite = TestSuite(name="Tagged Tests")
        suite.add_test(TestCase(
            prompt_id="greeting",
            name="test1",
            tags=["smoke"],
            expected_output="Hello!",
        ))
        suite.add_test(TestCase(
            prompt_id="greeting",
            name="test2",
            tags=["integration"],
            expected_output="Hello!",
        ))

        runner = PromptTestRunner(project_root=tmp_path)
        results = runner.run_tests_by_tag(suite, "smoke")

        assert len(results) == 1
        assert results[0].test_name == "test1"


class TestYamlSerialization:
    """Test YAML serialization of test suites."""

    def test_save_and_load_test_suite(self, tmp_path):
        """Test saving and loading a test suite."""
        # Create a test suite
        suite = TestSuite(
            name="Test Suite",
            description="A test suite",
        )
        suite.add_test(TestCase(
            prompt_id="greeting",
            name="test_greeting",
            inputs={"name": "Alice"},
            description="Test greeting",
            expected_output="Hello, Alice!",
            tags=["smoke"],
        ))
        suite.add_test(TestCase(
            prompt_id="farewell",
            name="test_farewell",
            inputs={"name": "Bob"},
            validation_config={
                "validation": [
                    {"type": "contains", "substring": "Bob"},
                ]
            },
        ))

        # Save to file
        yaml_file = tmp_path / "tests.yaml"
        save_test_suite_to_yaml(suite, yaml_file)

        # Load from file
        loaded_suite = load_test_suite_from_yaml(yaml_file)

        assert loaded_suite.name == suite.name
        assert loaded_suite.description == suite.description
        assert len(loaded_suite.test_cases) == 2

        # Check first test
        test1 = loaded_suite.test_cases[0]
        assert test1.prompt_id == "greeting"
        assert test1.name == "test_greeting"
        assert test1.inputs == {"name": "Alice"}
        assert test1.expected_output == "Hello, Alice!"
        assert "smoke" in test1.tags

        # Check second test
        test2 = loaded_suite.test_cases[1]
        assert test2.prompt_id == "farewell"
        assert test2.validator is not None

    def test_load_test_suite_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML."""
        yaml_file = tmp_path / "invalid.yaml"
        # Write a list instead of a dict at root level
        yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")

        # Should raise ValueError because root is not a dict
        with pytest.raises(ValueError, match="expected a dictionary"):
            load_test_suite_from_yaml(yaml_file)

    def test_load_test_suite_missing_required_fields(self, tmp_path):
        """Test loading test suite with missing required fields."""
        yaml_file = tmp_path / "missing_fields.yaml"
        yaml_file.write_text(
            "name: Test\ntests:\n  - name: test1\n",  # Missing prompt_id
            encoding="utf-8"
        )

        with pytest.raises(ValueError, match="prompt_id"):
            load_test_suite_from_yaml(yaml_file)


class TestTestReporter:
    """Test TestReporter class."""

    def test_print_summary(self, capsys):
        """Test printing test summary."""
        from prompt_vcs.testing import TestResult

        results = [
            TestResult(
                test_name="test1",
                prompt_id="p1",
                status=TestStatus.PASSED,
            ),
            TestResult(
                test_name="test2",
                prompt_id="p2",
                status=TestStatus.FAILED,
            ),
            TestResult(
                test_name="test3",
                prompt_id="p3",
                status=TestStatus.SKIPPED,
            ),
        ]

        TestReporter.print_summary(results)

        captured = capsys.readouterr()
        assert "Total:   3" in captured.out
        assert "Passed:  1" in captured.out
        assert "Failed:  1" in captured.out
        assert "Skipped: 1" in captured.out

    def test_print_detailed(self, capsys):
        """Test printing detailed results."""
        from prompt_vcs.testing import TestResult

        results = [
            TestResult(
                test_name="test_pass",
                prompt_id="p1",
                status=TestStatus.PASSED,
                duration_ms=10.5,
            ),
            TestResult(
                test_name="test_fail",
                prompt_id="p2",
                status=TestStatus.FAILED,
                error_message="Validation failed",
                duration_ms=5.2,
            ),
        ]

        TestReporter.print_detailed(results, verbose=False)

        captured = capsys.readouterr()
        assert "test_pass" in captured.out
        assert "test_fail" in captured.out
        assert "Validation failed" in captured.out