"""
Tests for prompt_vcs.extractor module.
"""

import warnings
import pytest
from pathlib import Path

from prompt_vcs.extractor import (
    extract_prompts_from_file,
    extract_prompts_from_directory,
    check_id_conflicts,
    PromptIdConflictError,
    ExtractedPrompt,
)


@pytest.fixture
def sample_code_file(tmp_path):
    """Create a sample Python file with prompts."""
    code = '''
from prompt_vcs import p, prompt

# Inline mode
greeting = p("user_greeting", "你好 {name}")
farewell = p("farewell", "再见，{name}！")

# Decorator mode
@prompt(id="system_core", default_version="v1")
def get_system_prompt(role: str):
    """
    你是一个乐于助人的助手，扮演的角色是 {role}。
    """
    pass
'''
    
    py_file = tmp_path / "app.py"
    py_file.write_text(code, encoding="utf-8")
    return py_file


@pytest.fixture
def fstring_code_file(tmp_path):
    """Create a sample file with f-string (should warn)."""
    code = '''
from prompt_vcs import p

name = "test"
# This should trigger a warning
msg = p("bad_prompt", f"Hello {name}")
'''
    
    py_file = tmp_path / "bad.py"
    py_file.write_text(code, encoding="utf-8")
    return py_file


class TestExtractPrompts:
    """Tests for prompt extraction."""
    
    def test_extract_p_calls(self, sample_code_file):
        """Test extracting p() function calls."""
        prompts = extract_prompts_from_file(sample_code_file)
        
        ids = [p.id for p in prompts]
        assert "user_greeting" in ids
        assert "farewell" in ids
    
    def test_extract_decorator(self, sample_code_file):
        """Test extracting @prompt decorators."""
        prompts = extract_prompts_from_file(sample_code_file)
        
        decorator_prompts = [p for p in prompts if p.is_decorator]
        assert len(decorator_prompts) == 1
        assert decorator_prompts[0].id == "system_core"
        assert "乐于助人" in decorator_prompts[0].default_content
    
    def test_fstring_warning(self, fstring_code_file):
        """Test that f-strings trigger a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            prompts = extract_prompts_from_file(fstring_code_file)
            
            # Should have warning about f-string
            assert any("f-string" in str(warning.message) for warning in w)
            
            # Should not extract the bad prompt
            ids = [p.id for p in prompts]
            assert "bad_prompt" not in ids
    
    def test_extract_from_directory(self, tmp_path):
        """Test extracting from a directory."""
        # Create multiple files
        (tmp_path / "a.py").write_text('from prompt_vcs import p\nmsg = p("a", "A")')
        (tmp_path / "b.py").write_text('from prompt_vcs import p\nmsg = p("b", "B")')
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.py").write_text('from prompt_vcs import p\nmsg = p("c", "C")')
        
        prompts = list(extract_prompts_from_directory(tmp_path))
        ids = [p.id for p in prompts]
        
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids


class TestIdConflicts:
    """Tests for ID conflict detection."""
    
    def test_no_conflict_same_content(self):
        """Test that same ID with same content is OK."""
        prompts = [
            ExtractedPrompt("test", "content", "a.py", 1),
            ExtractedPrompt("test", "content", "b.py", 1),
        ]
        
        # Should not raise
        check_id_conflicts(prompts)
    
    def test_conflict_different_content(self):
        """Test that same ID with different content raises error."""
        prompts = [
            ExtractedPrompt("test", "content A", "a.py", 1),
            ExtractedPrompt("test", "content B", "b.py", 1),
        ]
        
        with pytest.raises(PromptIdConflictError) as exc_info:
            check_id_conflicts(prompts)
        
        assert exc_info.value.prompt_id == "test"
        assert len(exc_info.value.locations) == 2
    
    def test_multiple_unique_ids(self):
        """Test multiple unique IDs don't conflict."""
        prompts = [
            ExtractedPrompt("a", "content A", "a.py", 1),
            ExtractedPrompt("b", "content B", "b.py", 1),
            ExtractedPrompt("c", "content C", "c.py", 1),
        ]
        
        # Should not raise
        check_id_conflicts(prompts)
