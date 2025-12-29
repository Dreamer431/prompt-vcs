"""
prompt-vcs: Git-native prompt management library for LLM applications.
"""

from prompt_vcs.api import p, prompt
from prompt_vcs.manager import PromptManager, get_manager
from prompt_vcs.validator import PromptValidator, ValidationRule, ValidationType
from prompt_vcs.testing import TestCase, TestSuite, PromptTestRunner
from prompt_vcs.codemod import migrate_file_content
from prompt_vcs.ab_testing import (
    ab_test,
    ABTestManager,
    ABTestConfig,
    ABTestVariant,
    ABTestRecord,
    ABTestResult,
)

__version__ = "0.5.0"
__all__ = [
    "p",
    "prompt",
    "PromptManager",
    "get_manager",
    "PromptValidator",
    "ValidationRule",
    "ValidationType",
    "TestCase",
    "TestSuite",
    "PromptTestRunner",
    "migrate_file_content",
    # A/B Testing
    "ab_test",
    "ABTestManager",
    "ABTestConfig",
    "ABTestVariant",
    "ABTestRecord",
    "ABTestResult",
]
