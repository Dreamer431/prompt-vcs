"""
Tests for prompt_vcs.cli module.

Integration tests for all CLI commands using Typer's CliRunner.
"""

import json
import pytest
from pathlib import Path

from typer.testing import CliRunner
from prompt_vcs.cli import app
from prompt_vcs.manager import LOCKFILE_NAME, PROMPTS_DIR, PROMPTS_FILE


runner = CliRunner()


class TestInitCommand:
    """Tests for 'pvcs init' command."""
    
    def test_init_creates_lockfile(self, tmp_path):
        """Test that init creates .prompt_lock.json."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        
        assert result.exit_code == 0
        assert (tmp_path / LOCKFILE_NAME).exists()
        
        # Verify lockfile content is valid JSON
        lockfile = json.loads((tmp_path / LOCKFILE_NAME).read_text())
        assert lockfile == {}
    
    def test_init_creates_prompts_yaml_by_default(self, tmp_path):
        """Test that init creates prompts.yaml in single-file mode (default)."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        
        assert result.exit_code == 0
        assert (tmp_path / PROMPTS_FILE).exists()
        assert not (tmp_path / PROMPTS_DIR).exists()
    
    def test_init_split_creates_prompts_directory(self, tmp_path):
        """Test that init --split creates prompts/ directory."""
        result = runner.invoke(app, ["init", str(tmp_path), "--split"])
        
        assert result.exit_code == 0
        assert (tmp_path / PROMPTS_DIR).exists()
        assert (tmp_path / PROMPTS_DIR).is_dir()
        assert not (tmp_path / PROMPTS_FILE).exists()
    
    def test_init_idempotent(self, tmp_path):
        """Test that init is idempotent (doesn't overwrite existing files)."""
        # First init
        runner.invoke(app, ["init", str(tmp_path)])
        
        # Modify lockfile
        lockfile_path = tmp_path / LOCKFILE_NAME
        lockfile_path.write_text('{"test": "v1"}', encoding="utf-8")
        
        # Second init
        result = runner.invoke(app, ["init", str(tmp_path)])
        
        assert result.exit_code == 0
        # Original content should be preserved
        content = lockfile_path.read_text()
        assert '"test"' in content


class TestScaffoldCommand:
    """Tests for 'pvcs scaffold' command."""
    
    @pytest.fixture
    def project_with_prompts(self, tmp_path):
        """Create a project with Python files containing prompts."""
        # Initialize project
        runner.invoke(app, ["init", str(tmp_path)])
        
        # Create src directory with Python file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        py_file = src_dir / "app.py"
        py_file.write_text('''
from prompt_vcs import p

greeting = p("user_greeting", "Hello {name}!")
''', encoding="utf-8")
        
        return tmp_path
    
    def test_scaffold_scans_directory(self, project_with_prompts):
        """Test that scaffold scans the directory for prompts."""
        src_dir = project_with_prompts / "src"
        
        result = runner.invoke(app, ["scaffold", str(src_dir)])
        
        assert result.exit_code == 0
        assert "user_greeting" in result.output
    
    def test_scaffold_dry_run(self, project_with_prompts):
        """Test that scaffold --dry-run doesn't create files."""
        src_dir = project_with_prompts / "src"
        prompts_file = project_with_prompts / PROMPTS_FILE
        original_content = prompts_file.read_text()
        
        result = runner.invoke(app, ["scaffold", str(src_dir), "--dry-run"])
        
        assert result.exit_code == 0
        assert "Dry run" in result.output
        # Content should be unchanged
        assert prompts_file.read_text() == original_content
    
    def test_scaffold_nonexistent_directory(self, tmp_path):
        """Test scaffold with nonexistent directory fails gracefully."""
        result = runner.invoke(app, ["scaffold", str(tmp_path / "nonexistent")])
        
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestSwitchCommand:
    """Tests for 'pvcs switch' command."""
    
    @pytest.fixture
    def project_with_versions(self, tmp_path):
        """Create a project with multiple prompt versions."""
        # Create lockfile
        lockfile_path = tmp_path / LOCKFILE_NAME
        lockfile_path.write_text('{}', encoding="utf-8")
        
        # Create prompts directory with versions
        prompt_dir = tmp_path / PROMPTS_DIR / "greeting"
        prompt_dir.mkdir(parents=True)
        
        (prompt_dir / "v1.yaml").write_text("""version: v1
description: "Simple greeting"
template: |
  Hello {name}!
""", encoding="utf-8")
        
        (prompt_dir / "v2.yaml").write_text("""version: v2
description: "Formal greeting"
template: |
  Dear {name}, welcome!
""", encoding="utf-8")
        
        return tmp_path
    
    def test_switch_updates_lockfile(self, project_with_versions):
        """Test that switch updates the lockfile."""
        result = runner.invoke(
            app, 
            ["switch", "greeting", "v2", "--project", str(project_with_versions)]
        )
        
        assert result.exit_code == 0
        
        lockfile = json.loads(
            (project_with_versions / LOCKFILE_NAME).read_text()
        )
        assert lockfile["greeting"] == "v2"
    
    def test_switch_nonexistent_version(self, project_with_versions):
        """Test that switch fails for nonexistent version."""
        result = runner.invoke(
            app,
            ["switch", "greeting", "v99", "--project", str(project_with_versions)]
        )
        
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestStatusCommand:
    """Tests for 'pvcs status' command."""
    
    def test_status_empty_lockfile(self, tmp_path):
        """Test status with empty lockfile."""
        lockfile_path = tmp_path / LOCKFILE_NAME
        lockfile_path.write_text('{}', encoding="utf-8")
        
        result = runner.invoke(app, ["status", "--project", str(tmp_path)])
        
        assert result.exit_code == 0
        assert "empty" in result.output.lower()
    
    def test_status_shows_locked_prompts(self, tmp_path):
        """Test status shows locked prompts."""
        # Create lockfile with entries
        lockfile_path = tmp_path / LOCKFILE_NAME
        lockfile_path.write_text('{"greeting": "v2", "summary": "v1"}', encoding="utf-8")
        
        # Create corresponding YAML files
        for prompt_id, version in [("greeting", "v2"), ("summary", "v1")]:
            prompt_dir = tmp_path / PROMPTS_DIR / prompt_id
            prompt_dir.mkdir(parents=True)
            (prompt_dir / f"{version}.yaml").write_text(
                f"version: {version}\ntemplate: test\n", 
                encoding="utf-8"
            )
        
        result = runner.invoke(app, ["status", "--project", str(tmp_path)])
        
        assert result.exit_code == 0
        assert "greeting" in result.output
        assert "summary" in result.output
        assert "v2" in result.output
        assert "v1" in result.output
    
    def test_status_no_lockfile(self, tmp_path):
        """Test status when lockfile doesn't exist."""
        result = runner.invoke(app, ["status", "--project", str(tmp_path)])
        
        assert result.exit_code == 1


class TestMigrateCommand:
    """Tests for 'pvcs migrate' command."""
    
    @pytest.fixture
    def project_with_code(self, tmp_path):
        """Create a project with Python code to migrate."""
        # Initialize project
        runner.invoke(app, ["init", str(tmp_path)])
        
        # Create Python file with hardcoded prompt
        py_file = tmp_path / "app.py"
        py_file.write_text('''
user = "Alice"
prompt = f"Hello {user}, welcome to the application!"
''', encoding="utf-8")
        
        return tmp_path
    
    def test_migrate_dry_run(self, project_with_code):
        """Test that migrate --dry-run shows candidates but doesn't modify."""
        py_file = project_with_code / "app.py"
        original = py_file.read_text()
        
        result = runner.invoke(
            app, 
            ["migrate", str(py_file), "--dry-run"]
        )
        
        assert result.exit_code == 0
        assert "Dry run" in result.output
        # File should be unchanged
        assert py_file.read_text() == original
    
    def test_migrate_applies_changes(self, project_with_code):
        """Test that migrate --yes applies changes."""
        py_file = project_with_code / "app.py"
        
        result = runner.invoke(
            app,
            ["migrate", str(py_file), "--yes"]
        )
        
        assert result.exit_code == 0
        
        # Check file was modified
        content = py_file.read_text()
        assert "from prompt_vcs import p" in content
        assert "p(" in content
    
    def test_migrate_clean_mode(self, project_with_code):
        """Test that migrate --clean extracts to YAML."""
        py_file = project_with_code / "app.py"
        
        result = runner.invoke(
            app,
            ["migrate", str(py_file), "--clean", "--yes"]
        )
        
        assert result.exit_code == 0
        
        # Check prompts.yaml was updated
        prompts_yaml = project_with_code / PROMPTS_FILE
        content = prompts_yaml.read_text()
        assert "app_prompt" in content
    
    def test_migrate_nonexistent_path(self, tmp_path):
        """Test migrate with nonexistent path fails gracefully."""
        result = runner.invoke(
            app,
            ["migrate", str(tmp_path / "nonexistent.py")]
        )
        
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestDiffCommand:
    """Tests for 'pvcs diff' command."""
    
    @pytest.fixture
    def project_with_versions(self, tmp_path):
        """Create a project with multiple prompt versions."""
        # Create lockfile
        lockfile_path = tmp_path / LOCKFILE_NAME
        lockfile_path.write_text('{}', encoding="utf-8")
        
        # Create prompts directory with versions
        prompt_dir = tmp_path / PROMPTS_DIR / "greeting"
        prompt_dir.mkdir(parents=True)
        
        (prompt_dir / "v1.yaml").write_text("""version: v1
description: "Simple greeting"
template: |
  Hello {name}!
""", encoding="utf-8")
        
        (prompt_dir / "v2.yaml").write_text("""version: v2
description: "Formal greeting"
template: |
  Dear {name}, welcome to our service!
""", encoding="utf-8")
        
        return tmp_path
    
    def test_diff_shows_differences(self, project_with_versions):
        """Test that diff shows differences between versions."""
        result = runner.invoke(
            app,
            ["diff", "greeting", "v1", "v2", "--project", str(project_with_versions)]
        )
        
        assert result.exit_code == 0
        assert "Diff" in result.output
        # Should show some diff content
        assert "Hello" in result.output or "Dear" in result.output
    
    def test_diff_identical_versions(self, project_with_versions):
        """Test diff with identical versions shows no differences."""
        result = runner.invoke(
            app,
            ["diff", "greeting", "v1", "v1", "--project", str(project_with_versions)]
        )
        
        assert result.exit_code == 0
        assert "No differences" in result.output
    
    def test_diff_nonexistent_version(self, project_with_versions):
        """Test diff with nonexistent version fails."""
        result = runner.invoke(
            app,
            ["diff", "greeting", "v1", "v99", "--project", str(project_with_versions)]
        )
        
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
    
    def test_diff_single_file_mode_error(self, tmp_path):
        """Test that diff shows error in single-file mode."""
        # Initialize in single-file mode
        runner.invoke(app, ["init", str(tmp_path)])
        
        result = runner.invoke(
            app,
            ["diff", "greeting", "v1", "v2", "--project", str(tmp_path)]
        )
        
        assert result.exit_code == 1
        assert "single-file" in result.output.lower()


class TestLogCommand:
    """Tests for 'pvcs log' command."""
    
    def test_log_no_git_repo(self, tmp_path):
        """Test log fails when not in a Git repository."""
        # Create lockfile but no .git
        (tmp_path / LOCKFILE_NAME).write_text('{}', encoding="utf-8")
        
        result = runner.invoke(
            app,
            ["log", "greeting", "--project", str(tmp_path)]
        )
        
        assert result.exit_code == 1
        assert "git" in result.output.lower()
    
    def test_log_prompt_not_found(self, tmp_path):
        """Test log fails when prompt doesn't exist."""
        # Create .git directory and lockfile
        (tmp_path / ".git").mkdir()
        (tmp_path / LOCKFILE_NAME).write_text('{}', encoding="utf-8")
        
        result = runner.invoke(
            app,
            ["log", "nonexistent", "--project", str(tmp_path)]
        )
        
        assert result.exit_code == 1

