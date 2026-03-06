"""
Tests for prompt_vcs.templates module - single file mode functions.
"""

from pathlib import Path
import pytest
import yaml

from prompt_vcs.templates import load_prompts_file, save_prompts_file, render_template


class TestLoadPromptsFile:
    """Tests for load_prompts_file function."""
    
    def test_load_prompts_file(self, tmp_path):
        """Test loading a valid prompts.yaml file."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("""greeting:
  description: "Greeting template"
  template: |
    Hello, {name}!

summary:
  description: "Summary template"
  template: |
    Summarize: {content}
""", encoding="utf-8")
        
        result = load_prompts_file(prompts_file)
        
        assert len(result) == 2
        assert "greeting" in result
        assert "summary" in result
        assert "Hello, {name}!" in result["greeting"]["template"]
        assert result["greeting"]["description"] == "Greeting template"
    
    def test_load_empty_file(self, tmp_path):
        """Test loading an empty prompts.yaml returns empty dict."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("", encoding="utf-8")
        
        result = load_prompts_file(prompts_file)
        assert result == {}
    
    def test_load_file_not_found(self, tmp_path):
        """Test loading non-existent file raises error."""
        prompts_file = tmp_path / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError):
            load_prompts_file(prompts_file)
    
    def test_load_invalid_format(self, tmp_path):
        """Test loading invalid format raises error."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("not a dict", encoding="utf-8")
        
        with pytest.raises(ValueError, match="expected a dictionary"):
            load_prompts_file(prompts_file)
    
    def test_load_missing_template(self, tmp_path):
        """Test loading prompt without template field raises error."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("""greeting:
  description: "No template"
""", encoding="utf-8")
        
        with pytest.raises(ValueError, match="Missing 'template' field"):
            load_prompts_file(prompts_file)

    def test_load_versions_only_entry_preserves_structure(self, tmp_path):
        """Test versions-only entries do not get fake base fields."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("""greeting:
  versions:
    v2:
      template: |
        Hello, {name}!
""", encoding="utf-8")

        result = load_prompts_file(prompts_file)

        assert result["greeting"] == {
            "versions": {
                "v2": {
                    "template": "Hello, {name}!\n",
                }
            }
        }
        assert "template" not in result["greeting"]
        assert "description" not in result["greeting"]


class TestSavePromptsFile:
    """Tests for save_prompts_file function."""
    
    def test_save_prompts_file(self, tmp_path):
        """Test saving prompts to a file."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts = {
            "greeting": {
                "description": "Greeting template",
                "template": "Hello, {name}!",
            },
            "summary": {
                "description": "Summary template",
                "template": "Summarize: {content}",
            },
        }
        
        save_prompts_file(prompts_file, prompts)
        
        # Verify file was created
        assert prompts_file.exists()
        
        # Verify content can be loaded back
        loaded = load_prompts_file(prompts_file)
        assert loaded["greeting"]["template"] == "Hello, {name}!"
        assert loaded["summary"]["template"] == "Summarize: {content}"
    
    def test_save_creates_parent_dirs(self, tmp_path):
        """Test that save_prompts_file creates parent directories."""
        prompts_file = tmp_path / "nested" / "dir" / "prompts.yaml"
        prompts = {
            "test": {
                "description": "Test",
                "template": "Test template",
            },
        }
        
        save_prompts_file(prompts_file, prompts)
        
        assert prompts_file.exists()
    
    def test_save_empty_prompts(self, tmp_path):
        """Test saving empty prompts dict."""
        prompts_file = tmp_path / "prompts.yaml"
        
        save_prompts_file(prompts_file, {})
        
        assert prompts_file.exists()
        loaded = load_prompts_file(prompts_file)
        assert loaded == {}

    def test_save_versions_only_round_trip(self, tmp_path):
        """Test versions-only entries round-trip without extra fields."""
        prompts_file = tmp_path / "prompts.yaml"
        prompts_file.write_text("""greeting:
  versions:
    v2:
      template: |
        Hello, {name}!
""", encoding="utf-8")

        prompts = load_prompts_file(prompts_file)
        save_prompts_file(prompts_file, prompts)

        saved = yaml.safe_load(prompts_file.read_text(encoding="utf-8"))
        assert saved == {
            "greeting": {
                "versions": {
                    "v2": {
                        "template": "Hello, {name}!\n",
                    }
                }
            }
        }


class TestRenderTemplate:
    """Tests for render_template."""

    def test_render_simple_placeholder(self):
        assert render_template("Hello {name}", name="World") == "Hello World"

    def test_render_jinja_placeholder(self):
        assert render_template("Hi {{ name }}", name="Ada") == "Hi Ada"

    def test_render_format_spec(self):
        assert render_template("Price: {price:.2f}", price=3.14159) == "Price: 3.14"

    def test_render_conversion(self):
        assert render_template("Value: {v!r}", v="x") == "Value: 'x'"
