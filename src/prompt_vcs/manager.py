"""
Core prompt manager: handles lockfile loading and prompt resolution.
"""

import inspect
import hashlib
import json
import os
import re
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from prompt_vcs.templates import load_yaml_template, load_prompts_file, render_template


# Lockfile and prompts file/directory names
LOCKFILE_NAME = ".prompt_lock.json"
PROMPTS_FILE = "prompts.yaml"  # Single-file mode
PROMPTS_DIR = "prompts"  # Multi-file mode
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _file_signature(path: Path) -> Optional[tuple[int, int, bytes]]:
    """Return a signature that also detects same-timestamp, same-size rewrites."""
    if not path.exists():
        return None
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).digest()
    return stat.st_mtime_ns, stat.st_size, digest


def validate_identifier(value: str, field_name: str = "Identifier") -> None:
    """Validate an identifier before using it in project-relative paths."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must not be empty")
    if value in {".", ".."} or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} may only contain letters, numbers, '.', '_' and '-'"
        )


@dataclass
class PromptDefinition:
    """Represents a prompt definition extracted from code."""
    id: str
    default_content: str
    source_file: str = ""
    line_number: int = 0


@dataclass
class PromptManager:
    """
    Singleton manager for loading lockfile and resolving prompts.
    
    The manager:
    1. Finds the project root by searching upward for .prompt_lock.json or .git
    2. Loads and caches the lockfile
    3. Resolves prompts based on lockfile or falls back to default content
    """
    
    _project_root: Optional[Path] = None
    _lockfile: dict[str, str] = field(default_factory=dict)
    _lockfile_loaded: bool = False
    _lockfile_signature: Optional[tuple[int, int, bytes]] = None
    _registry: dict[str, PromptDefinition] = field(default_factory=dict)
    _prompts_cache: dict[str, dict] = field(default_factory=dict)  # Cache for single-file mode
    _prompts_cache_loaded: bool = False
    _prompts_cache_signature: Optional[tuple[int, int, bytes]] = None
    
    def find_project_root(self, start_path: Optional[Path] = None) -> Optional[Path]:
        """
        Recursively search upward to find the project root.
        
        The project root is identified by:
        1. Presence of .prompt_lock.json
        2. Or presence of .git directory
        
        Args:
            start_path: Starting directory for search. If None, uses caller's file location.
            
        Returns:
            Path to project root, or None if not found
        """
        if start_path is None:
            # Get caller's file location from the call stack
            frame = inspect.currentframe()
            try:
                # Go up the call stack to find the actual caller (not this module)
                caller_frame = frame.f_back
                while caller_frame:
                    caller_file = caller_frame.f_code.co_filename
                    # Skip internal prompt_vcs modules
                    if "prompt_vcs" not in caller_file:
                        start_path = Path(caller_file).parent.resolve()
                        break
                    caller_frame = caller_frame.f_back
                
                if start_path is None:
                    start_path = Path.cwd()
            finally:
                del frame
        
        current = start_path.resolve()
        
        # Search upward
        while current != current.parent:
            # Check for lockfile
            if (current / LOCKFILE_NAME).exists():
                return current
            # Check for .git directory
            if (current / ".git").exists():
                return current
            current = current.parent
        
        # Check root directory as well
        if (current / LOCKFILE_NAME).exists():
            return current
        if (current / ".git").exists():
            return current
            
        return None
    
    def load_lockfile(self, force: bool = False) -> dict[str, str]:
        """
        Load the lockfile from the project root.
        
        Args:
            force: Force reload even if already loaded
            
        Returns:
            Dictionary mapping prompt IDs to version strings
        """
        if self._project_root is None:
            self._project_root = self.find_project_root()
        
        if self._project_root is None:
            self._lockfile = {}
            self._lockfile_loaded = True
            self._lockfile_signature = None
            return self._lockfile
        
        lockfile_path = self._project_root / LOCKFILE_NAME
        try:
            current_signature = _file_signature(lockfile_path)
        except OSError as exc:
            raise ValueError(
                f"Failed to inspect lockfile {lockfile_path}: {exc}"
            ) from exc

        if (
            self._lockfile_loaded
            and not force
            and self._lockfile_signature == current_signature
        ):
            return self._lockfile
        
        if not lockfile_path.exists():
            self._lockfile = {}
            self._lockfile_loaded = True
            self._lockfile_signature = None
            return self._lockfile
        
        try:
            with open(lockfile_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Failed to load lockfile {lockfile_path}: {exc}") from exc

        if not isinstance(loaded, dict) or not all(
            isinstance(prompt_id, str) and isinstance(version, str)
            for prompt_id, version in loaded.items()
        ):
            raise ValueError(
                f"Invalid lockfile {lockfile_path}: expected a JSON object "
                "mapping prompt IDs to version strings"
            )
        for prompt_id, version in loaded.items():
            validate_identifier(prompt_id, "Prompt ID")
            validate_identifier(version, "Version")

        self._lockfile = loaded
        
        self._lockfile_loaded = True
        self._lockfile_signature = current_signature
        return self._lockfile
    
    def save_lockfile(self, lockfile: Optional[dict[str, str]] = None) -> None:
        """
        Save the lockfile to the project root.
        
        Args:
            lockfile: Lockfile to save. If None, saves the current lockfile.
        """
        if lockfile is not None:
            self._lockfile = lockfile

        if not isinstance(self._lockfile, dict):
            raise ValueError("Lockfile must be a dictionary")
        for prompt_id, version in self._lockfile.items():
            validate_identifier(prompt_id, "Prompt ID")
            validate_identifier(version, "Version")
        
        if self._project_root is None:
            self._project_root = self.find_project_root()
        
        if self._project_root is None:
            raise RuntimeError("Cannot save lockfile: project root not found")
        
        lockfile_path = self._project_root / LOCKFILE_NAME
        
        lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=lockfile_path.parent,
                prefix=f".{lockfile_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(self._lockfile, temp_file, indent=2, ensure_ascii=False)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            os.replace(temp_path, lockfile_path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

        self._lockfile_loaded = True
        self._lockfile_signature = _file_signature(lockfile_path)
    
    def register_prompt(self, definition: PromptDefinition) -> None:
        """
        Register a prompt definition from code.
        
        Args:
            definition: The prompt definition to register
        """
        self._registry[definition.id] = definition
    
    def detect_mode(self) -> str:
        """
        Detect whether the project uses single-file or multi-file mode.
        
        Returns:
            "single" if prompts.yaml exists, "multi" otherwise
        """
        if self._project_root is None:
            self._project_root = self.find_project_root()
        
        if self._project_root is None:
            return "multi"  # Default to multi-file mode
        
        prompts_file = self._project_root / PROMPTS_FILE
        if prompts_file.exists():
            return "single"
        
        return "multi"
    
    def _load_prompts_cache(self, force: bool = False) -> dict[str, dict]:
        """
        Load and cache prompts from single-file prompts.yaml.
        
        Args:
            force: Force reload even if already loaded
            
        Returns:
            Dictionary mapping prompt IDs to their data
        """
        if self._project_root is None:
            self._prompts_cache = {}
            self._prompts_cache_loaded = True
            self._prompts_cache_signature = None
            return self._prompts_cache
        
        prompts_file = self._project_root / PROMPTS_FILE
        try:
            current_signature = _file_signature(prompts_file)
        except OSError as exc:
            warnings.warn(
                f"Failed to inspect prompts file {prompts_file}: {exc}. "
                "Treating as empty prompts.",
                RuntimeWarning,
                stacklevel=2,
            )
            current_signature = None

        if (
            self._prompts_cache_loaded
            and not force
            and self._prompts_cache_signature == current_signature
        ):
            return self._prompts_cache
        
        if not prompts_file.exists():
            self._prompts_cache = {}
            self._prompts_cache_loaded = True
            self._prompts_cache_signature = None
            return self._prompts_cache
        
        try:
            self._prompts_cache = load_prompts_file(prompts_file)
        except Exception as e:
            warnings.warn(
                f"Failed to load prompts file {prompts_file}: {e}. "
                f"Treating as empty prompts.",
                RuntimeWarning,
                stacklevel=2,
            )
            self._prompts_cache = {}
        
        self._prompts_cache_loaded = True
        self._prompts_cache_signature = current_signature
        return self._prompts_cache
    
    def get_prompt(
        self,
        prompt_id: str,
        default_content: Optional[str] = None,
        _default_version: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Get a prompt by ID, resolving from lockfile or using default.
        
        Resolution order:
        1. If lockfile specifies a version, load prompts/{id}/{version}.yaml
        2. If not in lockfile, try to load prompts/{id}/v1.yaml
        3. Otherwise, use default_content
        4. Render template with provided kwargs
        
        Args:
            prompt_id: Unique identifier for the prompt
            default_content: Optional fallback content if not found in files
            **kwargs: Variables to substitute in the template
            
        Returns:
            Rendered prompt string
            
        Raises:
            PromptNotFoundError: If prompt is not found and no default_content is provided
        """
        from prompt_vcs.api import PromptNotFoundError

        validate_identifier(prompt_id, "Prompt ID")
        if _default_version is not None:
            validate_identifier(_default_version, "Default version")
        
        # Ensure lockfile is loaded
        lockfile = self.load_lockfile()
        is_locked = prompt_id in lockfile
        version = lockfile.get(prompt_id) or _default_version
        
        template: Optional[str] = None
        mode = self.detect_mode()
        
        # Single-file mode: load from prompts.yaml
        if mode == "single":
            prompts_cache = self._load_prompts_cache()
            def _get_versioned_template(data: Optional[dict], ver: str) -> Optional[str]:
                if not data:
                    return None
                versions = data.get("versions")
                if not isinstance(versions, dict):
                    return None
                version_data = versions.get(ver)
                if isinstance(version_data, str):
                    return version_data
                if isinstance(version_data, dict) and "template" in version_data:
                    return version_data["template"]
                return None

            def _get_base_template(data: Optional[dict]) -> Optional[str]:
                if not isinstance(data, dict):
                    return None
                if "template" not in data:
                    return None
                return data["template"]

            if version:
                version_key = f"{prompt_id}@{version}"
                version_entry = prompts_cache.get(version_key)
                if isinstance(version_entry, dict) and "template" in version_entry:
                    template = version_entry["template"]
                else:
                    template = _get_versioned_template(prompts_cache.get(prompt_id), version)
                    if template is None and is_locked:
                        raise PromptNotFoundError(
                            f"Prompt '{prompt_id}' is locked to missing version "
                            f"'{version}' in prompts.yaml"
                        )

            if template is None:
                template = _get_base_template(prompts_cache.get(prompt_id))
        else:
            # Multi-file mode: check lockfile for version
            if version:
                if self._project_root:
                    yaml_path = self._project_root / PROMPTS_DIR / prompt_id / f"{version}.yaml"
                    
                    if yaml_path.exists():
                        try:
                            data = load_yaml_template(yaml_path)
                            template = data["template"]
                        except Exception as e:
                            warnings.warn(
                                f"Failed to load prompt '{prompt_id}' version '{version}' "
                                f"from {yaml_path}: {e}. Falling back to default content.",
                                RuntimeWarning,
                                stacklevel=2,
                            )
                    elif is_locked:
                        raise PromptNotFoundError(
                            f"Prompt '{prompt_id}' is locked to missing version "
                            f"'{version}' at {yaml_path}"
                        )

            # When no explicit default version is requested, use v1.yaml.
            if template is None and not is_locked and _default_version is None and self._project_root:
                yaml_path = self._project_root / PROMPTS_DIR / prompt_id / "v1.yaml"
                if yaml_path.exists():
                    try:
                        data = load_yaml_template(yaml_path)
                        template = data["template"]
                    except Exception as e:
                        warnings.warn(
                            f"Failed to load prompt '{prompt_id}' from {yaml_path}: {e}. "
                            f"Falling back to default content.",
                            RuntimeWarning,
                            stacklevel=2,
                        )
        
        # Fall back to default_content
        if template is None:
            template = default_content
        
        # If still no template, raise error
        if template is None:
            raise PromptNotFoundError(
                f"Prompt '{prompt_id}' not found. "
                f"Please run 'pvcs scaffold' to create the YAML file, "
                f"or check your lockfile configuration."
            )
        
        # Render the template
        return render_template(template, **kwargs)
    
    def set_project_root(self, path: Path) -> None:
        """
        Manually set the project root path.
        
        Args:
            path: Path to the project root
        """
        self._project_root = path.resolve()
        self._lockfile = {}  # Clear cached lockfile
        self._lockfile_loaded = False  # Force reload
        self._lockfile_signature = None
        self._prompts_cache = {}  # Clear cached prompts
        self._prompts_cache_loaded = False
        self._prompts_cache_signature = None

    def reload(self) -> None:
        """Invalidate all file-backed caches for the next prompt resolution."""
        self._lockfile_loaded = False
        self._lockfile_signature = None
        self._prompts_cache_loaded = False
        self._prompts_cache_signature = None
    
    @property
    def project_root(self) -> Optional[Path]:
        """Get the project root path."""
        if self._project_root is None:
            self._project_root = self.find_project_root()
        return self._project_root


# Global singleton instance
_manager: Optional[PromptManager] = None


def get_manager() -> PromptManager:
    """Get the global PromptManager singleton."""
    global _manager
    if _manager is None:
        _manager = PromptManager()
    return _manager


def reset_manager() -> None:
    """Reset the global manager (useful for testing)."""
    global _manager
    _manager = None
