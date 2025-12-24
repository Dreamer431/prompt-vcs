"""
Pytest configuration and fixtures for prompt-vcs tests.
"""

import gc
import os
import sys
import shutil
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config):
    """
    Configure pytest to use a more accessible temp directory on Windows.
    
    On Windows, the default temp directory in AppData\Local\Temp can have
    permission issues during cleanup. Using a simpler path helps avoid this.
    """
    if sys.platform == "win32":
        # Use a simpler temp directory path on Windows
        # This helps avoid permission errors during cleanup
        base_tmp = Path(tempfile.gettempdir()) / "pytest_prompt_vcs"
        base_tmp.mkdir(exist_ok=True)
        config.option.basetemp = str(base_tmp)


@pytest.fixture(autouse=True)
def auto_reset_manager():
    """
    Automatically reset the PromptManager singleton before and after each test.
    
    This ensures:
    1. Each test starts with a fresh manager instance
    2. No file handles are retained from previous tests
    3. Windows temporary directory cleanup works correctly
    """
    from prompt_vcs.manager import reset_manager
    
    # Reset before test
    reset_manager()
    
    yield
    
    # Reset after test to release any file handles
    reset_manager()
    
    # Force garbage collection to close any lingering file handles
    gc.collect()


def pytest_sessionfinish(session, exitstatus):
    """
    Clean up temporary directory after all tests complete.
    """
    if sys.platform == "win32":
        gc.collect()
        base_tmp = Path(tempfile.gettempdir()) / "pytest_prompt_vcs"
        if base_tmp.exists():
            try:
                shutil.rmtree(base_tmp, ignore_errors=True)
            except Exception:
                pass  # Ignore cleanup errors
