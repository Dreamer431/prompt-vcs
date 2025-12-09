"""
Tests for prompt_vcs.codemod module.
"""

import pytest

from prompt_vcs.codemod import (
    sanitize_variable_name,
    is_complex_expression,
    extract_fstring_parts,
    migrate_file_content,
    MigrationCandidate,
)
import libcst as cst


class TestSanitizeVariableName:
    """Tests for variable name sanitization."""
    
    def test_simple_name(self):
        """Test simple variable names pass through."""
        assert sanitize_variable_name("user") == "user"
        assert sanitize_variable_name("name") == "name"
    
    def test_attribute_access(self):
        """Test attribute access is converted to underscore."""
        assert sanitize_variable_name("user.name") == "user_name"
        assert sanitize_variable_name("obj.attr.sub") == "obj_attr_sub"
    
    def test_dict_string_access(self):
        """Test dictionary string access is converted."""
        assert sanitize_variable_name("data['score']") == "data_score"
        assert sanitize_variable_name('data["key"]') == "data_key"
    
    def test_dict_numeric_access(self):
        """Test dictionary numeric access is converted."""
        assert sanitize_variable_name("items[0]") == "items_0"
        assert sanitize_variable_name("arr[10]") == "arr_10"
    
    def test_complex_access(self):
        """Test complex access patterns."""
        assert sanitize_variable_name("user.data['score']") == "user_data_score"


class TestIsComplexExpression:
    """Tests for complex expression detection."""
    
    def test_simple_variable(self):
        """Test simple variables are not complex."""
        assert not is_complex_expression("user")
        assert not is_complex_expression("name")
    
    def test_attribute_access(self):
        """Test attribute access is not complex."""
        assert not is_complex_expression("user.name")
    
    def test_dict_access(self):
        """Test dictionary access is not complex."""
        assert not is_complex_expression("data['key']")
    
    def test_function_call(self):
        """Test function calls are complex."""
        assert is_complex_expression("func()")
        assert is_complex_expression("obj.method()")
    
    def test_operators(self):
        """Test operators are complex."""
        assert is_complex_expression("x + 1")
        assert is_complex_expression("a - b")
        assert is_complex_expression("x * 2")


class TestExtractFstringParts:
    """Tests for f-string parsing."""
    
    def test_simple_fstring(self):
        """Test simple f-string extraction."""
        code = 'f"Hello {name}"'
        fstring = cst.parse_expression(code)
        template, parts, has_complex = extract_fstring_parts(fstring)
        
        assert template == "Hello {name}"
        assert len(parts) == 1
        assert parts[0].placeholder == "name"
        assert parts[0].expression == "name"
        assert not has_complex
    
    def test_fstring_with_format_spec(self):
        """Test f-string with format specification."""
        code = 'f"Price: {price:.2f}"'
        fstring = cst.parse_expression(code)
        template, parts, has_complex = extract_fstring_parts(fstring)
        
        assert template == "Price: {price:.2f}"
        assert len(parts) == 1
        assert parts[0].placeholder == "price"
        assert ":.2f" in parts[0].format_spec
    
    def test_fstring_with_attribute(self):
        """Test f-string with attribute access."""
        code = 'f"Hello {user.name}"'
        fstring = cst.parse_expression(code)
        template, parts, has_complex = extract_fstring_parts(fstring)
        
        assert template == "Hello {user_name}"
        assert len(parts) == 1
        assert parts[0].placeholder == "user_name"
        assert parts[0].expression == "user.name"
    
    def test_fstring_complex_skipped(self):
        """Test that complex expressions are flagged."""
        code = 'f"Result: {x + 1}"'
        fstring = cst.parse_expression(code)
        template, parts, has_complex = extract_fstring_parts(fstring)
        
        assert has_complex


class TestMigrateFileContent:
    """Tests for file content migration."""
    
    def test_simple_prompt_migration(self):
        """Test migration of a simple prompt string."""
        content = '''
prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 1
        assert candidates[0].variable_name == "prompt"
        assert "p(" in modified
        assert "from prompt_vcs import p" in modified
    
    def test_fstring_migration(self):
        """Test migration of an f-string prompt."""
        content = '''
user = "Alice"
prompt = f"Hello {user}, welcome to the system"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 1
        assert "p(" in modified
        assert "user=user" in modified
    
    def test_short_string_skipped(self):
        """Test that short strings are skipped."""
        content = '''
prompt = "Short"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 0
        assert modified.strip() == content.strip()
    
    def test_non_prompt_variable_skipped(self):
        """Test that non-prompt variables are skipped."""
        content = '''
message = "This is a long message that should not be migrated"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 0
    
    def test_format_spec_preserved(self):
        """Test that format specs are preserved."""
        content = '''
price = 99.99
price_msg = f"Price: {price:.2f} USD"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 1
        assert ":.2f" in modified
    
    def test_attribute_access_sanitized(self):
        """Test that attribute access is properly sanitized."""
        content = '''
class User:
    name = "Alice"
user = User()
greeting_template = f"Hello {user.name}, welcome!"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 1
        assert "user_name=user.name" in modified
    
    def test_complex_expression_skipped(self):
        """Test that complex expressions are skipped."""
        content = '''
complex_prompt = f"Result: {func()}"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 0
    
    def test_import_idempotency(self):
        """Test that import is not added if it already exists."""
        content = '''
from prompt_vcs import p

prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        # 确保只出现一次 import，而不是两个
        assert modified.count("from prompt_vcs import p") == 1
    
    def test_future_import_position(self):
        """Test that prompt_vcs import is added AFTER __future__ imports."""
        content = '''from __future__ import annotations
import os

prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        lines = modified.strip().split('\n')
        # 确保第一行依然是 __future__，而不是 prompt_vcs
        assert "from __future__" in lines[0]
        assert "from prompt_vcs import p" in modified
    
    def test_nested_scope_migration(self):
        """Test migration within a function scope."""
        content = '''
def get_greeting(name):
    prompt = f"Hello {name}, welcome to the app"
    return prompt
'''
        modified, candidates = migrate_file_content(content, "test.py", apply_changes=True)
        
        assert len(candidates) == 1
        # 确保 import 加到了文件最上面
        assert "from prompt_vcs import p" in modified
        # 确保函数体内的代码被修改了
        assert "p(" in modified
        assert "name=name" in modified


class TestCleanModeMigration:
    """Tests for clean_mode migration."""
    
    def test_clean_mode_generates_no_default(self, tmp_path):
        """Test clean_mode generates p() without default content."""
        content = '''
prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        # In clean mode, p() should only have ID and no default string
        assert 'p("test_prompt")' in modified
        # Should NOT contain the original string in the p() call
        assert '"Hello world, this is a test prompt"' not in modified
    
    def test_clean_mode_writes_yaml(self, tmp_path):
        """Test clean_mode writes YAML file."""
        content = '''
prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        # Check YAML file was created
        yaml_path = tmp_path / "prompts" / "test_prompt" / "v1.yaml"
        assert yaml_path.exists()
        
        # Check content
        yaml_content = yaml_path.read_text(encoding="utf-8")
        assert "Hello world, this is a test prompt" in yaml_content
        assert "version: v1" in yaml_content
    
    def test_clean_mode_skips_existing_yaml(self, tmp_path):
        """Test clean_mode skips existing YAML files."""
        # Pre-create YAML file
        yaml_dir = tmp_path / "prompts" / "test_prompt"
        yaml_dir.mkdir(parents=True)
        yaml_path = yaml_dir / "v1.yaml"
        yaml_path.write_text("version: v1\ntemplate: Existing content\n", encoding="utf-8")
        
        content = '''
prompt = "New content that should not overwrite"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        # Check YAML file was NOT overwritten
        yaml_content = yaml_path.read_text(encoding="utf-8")
        assert "Existing content" in yaml_content
        assert "New content that should not overwrite" not in yaml_content
    
    def test_clean_mode_with_fstring(self, tmp_path):
        """Test clean_mode with f-string extracts variables correctly."""
        content = '''
user = "Alice"
prompt = f"Hello {user}, welcome to the system"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        # Should have p() with ID and kwargs only, no template
        assert 'p("test_prompt", user=user)' in modified
        # Check YAML was created with template
        yaml_path = tmp_path / "prompts" / "test_prompt" / "v1.yaml"
        assert yaml_path.exists()
        yaml_content = yaml_path.read_text(encoding="utf-8")
        assert "{user}" in yaml_content


class TestSingleFileModeCleanMigration:
    """Tests for single-file mode (prompts.yaml) clean migration."""
    
    def test_single_file_mode_detection(self, tmp_path):
        """Test that single-file mode is detected when prompts.yaml exists."""
        # Create prompts.yaml to trigger single-file mode
        prompts_yaml = tmp_path / "prompts.yaml"
        prompts_yaml.write_text(
            "# Empty prompts file\n", 
            encoding="utf-8"
        )
        
        content = '''
prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        # In clean mode, should generate p() without default
        assert 'p("test_prompt")' in modified
        
        # Should write to prompts.yaml, NOT create prompts/test_prompt/v1.yaml
        multi_file_path = tmp_path / "prompts" / "test_prompt" / "v1.yaml"
        assert not multi_file_path.exists()
        
        # Check prompts.yaml was updated
        yaml_content = prompts_yaml.read_text(encoding="utf-8")
        assert "test_prompt" in yaml_content
        assert "Hello world, this is a test prompt" in yaml_content
    
    def test_single_file_mode_appends_to_existing(self, tmp_path):
        """Test that single-file mode appends to existing prompts.yaml."""
        # Create prompts.yaml with existing content
        prompts_yaml = tmp_path / "prompts.yaml"
        prompts_yaml.write_text(
            "existing_prompt:\n"
            "  description: \"Existing prompt\"\n"
            "  template: \"I already exist\"\n",
            encoding="utf-8"
        )
        
        content = '''
new_template = "This is a brand new template for testing"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        
        # Check both prompts exist in the file
        yaml_content = prompts_yaml.read_text(encoding="utf-8")
        assert "existing_prompt" in yaml_content
        assert "test_new_template" in yaml_content
        assert "I already exist" in yaml_content
        assert "This is a brand new template for testing" in yaml_content
    
    def test_single_file_mode_skips_duplicate(self, tmp_path):
        """Test that single-file mode skips prompts that already exist in prompts.yaml."""
        # Create prompts.yaml with a prompt that has the same ID
        prompts_yaml = tmp_path / "prompts.yaml"
        prompts_yaml.write_text(
            "test_prompt:\n"
            "  description: \"Original\"\n"
            "  template: \"Original content\"\n",
            encoding="utf-8"
        )
        
        content = '''
prompt = "New content that should NOT overwrite"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        # The code should still be migrated
        assert len(candidates) == 1
        assert 'p("test_prompt")' in modified
        
        # But the YAML should NOT be overwritten
        yaml_content = prompts_yaml.read_text(encoding="utf-8")
        assert "Original content" in yaml_content
        assert "New content that should NOT overwrite" not in yaml_content
    
    def test_single_file_mode_with_fstring(self, tmp_path):
        """Test single-file mode correctly handles f-strings."""
        prompts_yaml = tmp_path / "prompts.yaml"
        prompts_yaml.write_text("# Empty\n", encoding="utf-8")
        
        content = '''
user = "Alice"
greeting_template = f"Welcome, {user}! Nice to see you here."
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        assert 'p("test_greeting_template", user=user)' in modified
        
        # Check template was saved with placeholder
        yaml_content = prompts_yaml.read_text(encoding="utf-8")
        assert "test_greeting_template" in yaml_content
        assert "{user}" in yaml_content
    
    def test_multi_file_mode_when_no_prompts_yaml(self, tmp_path):
        """Test that multi-file mode is used when prompts.yaml does not exist."""
        # Ensure prompts.yaml does NOT exist
        prompts_yaml = tmp_path / "prompts.yaml"
        assert not prompts_yaml.exists()
        
        content = '''
prompt = "Hello world, this is a test prompt"
'''
        modified, candidates = migrate_file_content(
            content, 
            "test.py", 
            apply_changes=True,
            clean_mode=True,
            project_root=tmp_path,
        )
        
        assert len(candidates) == 1
        
        # Should create prompts/test_prompt/v1.yaml (multi-file mode)
        multi_file_path = tmp_path / "prompts" / "test_prompt" / "v1.yaml"
        assert multi_file_path.exists()
        
        yaml_content = multi_file_path.read_text(encoding="utf-8")
        assert "Hello world, this is a test prompt" in yaml_content
