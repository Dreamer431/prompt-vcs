"""
Tests for prompt_vcs.api module.
"""

import json
import pytest
from pathlib import Path

from prompt_vcs.api import p, prompt
from prompt_vcs.manager import reset_manager, get_manager, LOCKFILE_NAME, PROMPTS_DIR


@pytest.fixture(autouse=True)
def reset_manager_fixture():
    """Reset the manager before each test."""
    reset_manager()
    yield
    reset_manager()


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
  尊敬的 {{ name }}，您好！
""", encoding="utf-8")
    
    # Set project root
    mgr = get_manager()
    mgr.set_project_root(tmp_path)
    
    return tmp_path


class TestPFunction:
    """Tests for the p() function."""
    
    def test_basic_usage(self):
        """Test basic p() usage without lockfile."""
        result = p("test_prompt", "你好 {{ name }}", name="世界")
        assert result == "你好 世界"
    
    def test_with_lockfile(self, temp_project):
        """Test p() with a locked version."""
        result = p("greeting", "默认问候 {{ name }}", name="测试")
        assert "尊敬的 测试，您好！" in result
    
    def test_fallback_when_not_locked(self, temp_project):
        """Test p() falls back to default when not in lockfile."""
        result = p("unknown_prompt", "默认内容 {{ value }}", value="123")
        assert result == "默认内容 123"
    
    def test_multiple_variables(self):
        """Test p() with multiple variables."""
        result = p("multi", "{{ a }} + {{ b }} = {{ c }}", a=1, b=2, c=3)
        assert result == "1 + 2 = 3"


class TestPromptDecorator:
    """Tests for the @prompt decorator."""
    
    def test_basic_usage(self):
        """Test basic decorator usage."""
        @prompt(id="test_system_prompt_decorator")
        def get_system(role: str):
            """你是一个 {{ role }}。"""
            pass
        
        result = get_system(role="助手")
        assert result == "你是一个 助手。"
    
    def test_multiline_docstring(self):
        """Test decorator with multiline docstring."""
        @prompt(id="complex_prompt")
        def get_complex(name: str, task: str):
            """
            你好，{{ name }}！
            你的任务是：{{ task }}
            """
            pass
        
        result = get_complex(name="Claude", task="回答问题")
        assert "你好，Claude！" in result
        assert "你的任务是：回答问题" in result
    
    def test_default_version(self):
        """Test decorator with default_version parameter."""
        @prompt(id="versioned_prompt", default_version="v1")
        def get_versioned():
            """这是默认版本的内容。"""
            pass
        
        result = get_versioned()
        assert result == "这是默认版本的内容。"
    
    def test_with_lockfile(self, temp_project):
        """Test decorator respects lockfile."""
        @prompt(id="greeting")
        def get_greeting(name: str):
            """简单问候 {{ name }}"""
            pass
        
        result = get_greeting(name="测试用户")
        # Should use v2.yaml from lockfile
        assert "尊敬的 测试用户，您好！" in result


class TestCleanMode:
    """Tests for clean mode (p() without default_content)."""
    
    def test_no_default_loads_from_yaml(self, tmp_path):
        """Test p() without default_content loads from YAML file."""
        # Setup project structure
        lockfile_path = tmp_path / LOCKFILE_NAME
        with open(lockfile_path, "w") as f:
            json.dump({}, f)
        
        # Create YAML file
        prompts_dir = tmp_path / PROMPTS_DIR / "clean_test"
        prompts_dir.mkdir(parents=True)
        v1_yaml = prompts_dir / "v1.yaml"
        v1_yaml.write_text("""version: v1
description: "Test prompt"
template: |
  Clean mode test: {{ value }}
""", encoding="utf-8")
        
        # Set project root
        mgr = get_manager()
        mgr.set_project_root(tmp_path)
        
        # Call p() without default_content
        result = p("clean_test", value="success")
        assert "Clean mode test: success" in result
    
    def test_no_default_no_yaml_raises_error(self, tmp_path):
        """Test p() without default_content raises error when YAML not found."""
        from prompt_vcs.api import PromptNotFoundError
        
        # Setup project structure without YAML file
        lockfile_path = tmp_path / LOCKFILE_NAME
        with open(lockfile_path, "w") as f:
            json.dump({}, f)
        
        # Set project root
        mgr = get_manager()
        mgr.set_project_root(tmp_path)
        
        # Call p() without default_content should raise
        with pytest.raises(PromptNotFoundError) as excinfo:
            p("nonexistent_prompt", name="test")
        
        assert "nonexistent_prompt" in str(excinfo.value)
        assert "pvcs scaffold" in str(excinfo.value)
    
    def test_loads_from_v1_yaml_without_lockfile(self, tmp_path):
        """Test p() loads from v1.yaml even when not in lockfile."""
        # Setup project without lockfile entry
        lockfile_path = tmp_path / LOCKFILE_NAME
        with open(lockfile_path, "w") as f:
            json.dump({}, f)  # Empty lockfile
        
        # Create v1.yaml
        prompts_dir = tmp_path / PROMPTS_DIR / "auto_load"
        prompts_dir.mkdir(parents=True)
        v1_yaml = prompts_dir / "v1.yaml"
        v1_yaml.write_text("""version: v1
description: "Auto load test"
template: |
  Auto loaded: {{ msg }}
""", encoding="utf-8")
        
        mgr = get_manager()
        mgr.set_project_root(tmp_path)
        
        # Should load v1.yaml automatically
        result = p("auto_load", msg="works")
        assert "Auto loaded: works" in result

