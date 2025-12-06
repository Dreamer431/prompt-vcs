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

