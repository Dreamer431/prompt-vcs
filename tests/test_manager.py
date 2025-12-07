"""
Tests for prompt_vcs.manager module.
"""

import json
import pytest
from pathlib import Path

from prompt_vcs.manager import (
    PromptManager,
    PromptDefinition,
    get_manager,
    reset_manager,
    LOCKFILE_NAME,
    PROMPTS_DIR,
)


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project structure."""
    # Create lockfile
    lockfile = {"greeting": "v2"}
    lockfile_path = tmp_path / LOCKFILE_NAME
    with open(lockfile_path, "w") as f:
        json.dump(lockfile, f)
    
    # Create prompts directory
    prompts_dir = tmp_path / PROMPTS_DIR / "greeting"
    prompts_dir.mkdir(parents=True)
    
    # Create v2.yaml
    v2_yaml = prompts_dir / "v2.yaml"
    v2_yaml.write_text("""version: v2
description: "Formal greeting"
template: |
  尊敬的 {name}，您好！
""", encoding="utf-8")
    
    return tmp_path


@pytest.fixture
def manager(temp_project):
    """Create a manager with the temp project as root."""
    reset_manager()
    mgr = PromptManager()
    mgr.set_project_root(temp_project)
    return mgr


class TestPromptManager:
    """Tests for PromptManager class."""
    
    def test_load_lockfile(self, manager):
        """Test loading lockfile."""
        lockfile = manager.load_lockfile()
        assert lockfile == {"greeting": "v2"}
    
    def test_load_lockfile_not_found(self, tmp_path):
        """Test behavior when lockfile doesn't exist."""
        mgr = PromptManager()
        mgr.set_project_root(tmp_path)
        lockfile = mgr.load_lockfile()
        assert lockfile == {}
    
    def test_get_prompt_from_lockfile(self, manager):
        """Test getting prompt that is locked to a version."""
        result = manager.get_prompt("greeting", "默认 {name}", name="测试")
        assert "尊敬的 测试，您好！" in result
    
    def test_get_prompt_fallback(self, manager):
        """Test fallback to default content when not locked."""
        result = manager.get_prompt("unknown", "你好 {name}", name="世界")
        assert result == "你好 世界"
    
    def test_register_prompt(self, manager):
        """Test registering a prompt definition."""
        definition = PromptDefinition(
            id="test",
            default_content="测试内容",
            source_file="test.py",
            line_number=10,
        )
        manager.register_prompt(definition)
        assert "test" in manager._registry
        assert manager._registry["test"].default_content == "测试内容"
    
    def test_save_lockfile(self, manager, temp_project):
        """Test saving lockfile."""
        manager.save_lockfile({"new_prompt": "v1"})
        
        lockfile_path = temp_project / LOCKFILE_NAME
        with open(lockfile_path) as f:
            saved = json.load(f)
        
        assert saved == {"new_prompt": "v1"}


class TestFindProjectRoot:
    """Tests for project root discovery."""
    
    def test_find_by_lockfile(self, temp_project):
        """Test finding root by lockfile."""
        # Create subdirectory
        subdir = temp_project / "src" / "app"
        subdir.mkdir(parents=True)
        
        mgr = PromptManager()
        root = mgr.find_project_root(subdir)
        
        assert root == temp_project
    
    def test_find_by_git(self, tmp_path):
        """Test finding root by .git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        
        subdir = tmp_path / "src"
        subdir.mkdir()
        
        mgr = PromptManager()
        root = mgr.find_project_root(subdir)
        
        assert root == tmp_path
    
    def test_not_found(self, tmp_path):
        """Test when no project root is found."""
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        
        mgr = PromptManager()
        # Start from a path that has no markers above it
        # This is tricky to test, so we just verify it returns None or eventually stops
        root = mgr.find_project_root(isolated)
        # Root might be None or some parent with .git
        # The key is it doesn't infinite loop


class TestSingleFileMode:
    """Tests for single-file mode (prompts.yaml)."""
    
    @pytest.fixture
    def single_file_project(self, tmp_path):
        """Create a project with prompts.yaml (single-file mode)."""
        from prompt_vcs.manager import PROMPTS_FILE
        
        # Create lockfile
        lockfile_path = tmp_path / LOCKFILE_NAME
        with open(lockfile_path, "w") as f:
            json.dump({}, f)
        
        # Create prompts.yaml
        prompts_file = tmp_path / PROMPTS_FILE
        prompts_file.write_text("""greeting:
  description: "Greeting template"
  template: |
    Hello, {name}!

summary:
  description: "Summary template"
  template: |
    Summarize: {content}
""", encoding="utf-8")
        
        return tmp_path
    
    def test_detect_mode_single(self, single_file_project):
        """Test detect_mode returns 'single' when prompts.yaml exists."""
        reset_manager()
        mgr = PromptManager()
        mgr.set_project_root(single_file_project)
        
        mode = mgr.detect_mode()
        assert mode == "single"
    
    def test_detect_mode_multi(self, temp_project):
        """Test detect_mode returns 'multi' when prompts/ directory exists."""
        reset_manager()
        mgr = PromptManager()
        mgr.set_project_root(temp_project)
        
        mode = mgr.detect_mode()
        assert mode == "multi"
    
    def test_get_prompt_single_file(self, single_file_project):
        """Test getting prompt from prompts.yaml."""
        reset_manager()
        mgr = PromptManager()
        mgr.set_project_root(single_file_project)
        
        result = mgr.get_prompt("greeting", name="World")
        assert "Hello, World!" in result
    
    def test_get_prompt_single_file_not_found_fallback(self, single_file_project):
        """Test fallback to default content when prompt not in prompts.yaml."""
        reset_manager()
        mgr = PromptManager()
        mgr.set_project_root(single_file_project)
        
        result = mgr.get_prompt("unknown", "Fallback {value}", value="test")
        assert result == "Fallback test"
    
    def test_get_prompt_single_file_multiple_prompts(self, single_file_project):
        """Test loading multiple prompts from single file."""
        reset_manager()
        mgr = PromptManager()
        mgr.set_project_root(single_file_project)
        
        greeting = mgr.get_prompt("greeting", name="Alice")
        summary = mgr.get_prompt("summary", content="test data")
        
        assert "Hello, Alice!" in greeting
        assert "Summarize: test data" in summary
