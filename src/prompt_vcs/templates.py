"""
Jinja2 template rendering utilities.
"""

from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


# Create a sandboxed Jinja2 environment for safe template rendering
# SandboxedEnvironment prevents access to private attributes and dangerous methods
_env = SandboxedEnvironment(undefined=StrictUndefined)


def _pyformat(value: Any, spec: str) -> str:
    """Format a value using Python's format mini-language."""
    return format(value, spec)


_env.filters["pyformat"] = _pyformat
_env.filters["pyrepr"] = repr
_env.filters["pystr"] = str
_env.filters["pyascii"] = ascii


def render_template(template_str: str, **kwargs: Any) -> str:
    """
    Render a template string with the given variables.
    
    Supports both simple {variable} syntax and Jinja2 {{ variable }} syntax.
    Simple {var} placeholders are automatically converted to Jinja2 format.
    
    Args:
        template_str: The template string with {variable} or {{ variable }} placeholders
        **kwargs: Variables to substitute in the template
        
    Returns:
        Rendered string
        
    Raises:
        UndefinedError: If a required variable is not provided
    """
    import re
    
    # Convert {var}, {var:spec}, {var!r} to Jinja2 expressions.
    # But don't convert {{ var }} (already Jinja2 format).
    placeholder_re = re.compile(r"\{([a-zA-Z_]\w*)(?:!([rsa]))?(?::([^{}]+))?\}")

    def convert_simple_placeholder(template: str) -> str:
        # First, protect existing Jinja2 syntax by replacing temporarily
        protected = template.replace("{{", "\x00\x00").replace("}}", "\x01\x01")

        def repl(match: re.Match) -> str:
            name, conv, spec = match.group(1), match.group(2), match.group(3)
            expr = name
            if conv:
                conv_filter = {"r": "pyrepr", "s": "pystr", "a": "pyascii"}[conv]
                expr = f"{expr}|{conv_filter}"
            if spec is not None:
                escaped = spec.replace("\\", "\\\\").replace('"', '\\"')
                expr = f'{expr}|pyformat("{escaped}")'
            return "{{ " + expr + " }}"

        converted = placeholder_re.sub(repl, protected)
        return converted.replace("\x00\x00", "{{").replace("\x01\x01", "}}")

    jinja_template = convert_simple_placeholder(template_str)
    template = _env.from_string(jinja_template)
    return template.render(**kwargs)


def load_yaml_template(path: Path) -> dict[str, Any]:
    """
    Load a prompt template from a YAML file.
    
    Expected YAML format:
        version: v1
        description: "Description of the prompt"
        template: |
            Your prompt template here with {variables}
    
    Args:
        path: Path to the YAML file
        
    Returns:
        Dictionary with version, description, and template keys
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    # Validate required fields
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML format in {path}: expected a dictionary")
    
    if "template" not in data:
        raise ValueError(f"Missing 'template' field in {path}")
    
    return {
        "version": data.get("version", "v1"),
        "description": data.get("description", ""),
        "template": data["template"],
    }


def save_yaml_template(
    path: Path,
    template: str,
    version: str = "v1",
    description: str = "",
) -> None:
    """
    Save a prompt template to a YAML file.
    
    Args:
        path: Path to save the YAML file
        template: The template string
        version: Version identifier
        description: Description of the prompt
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": version,
        "description": description,
        "template": template,
    }
    
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_prompts_file(path: Path) -> dict[str, dict]:
    """
    Load all prompts from a single prompts.yaml file.
    
    Expected YAML format:
        greeting:
          description: "Greeting template"
          template: |
            Hello, {name}!
        
        summary:
          description: "Summary template"
          template: |
            Summarize: {content}
    
    Args:
        path: Path to the prompts.yaml file
        
    Returns:
        Dictionary mapping prompt IDs to their data (template, description)
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if data is None:
        return {}
    
    if not isinstance(data, dict):
        raise ValueError("Invalid prompts.yaml format: expected a dictionary at root level")
    
    result = {}
    for prompt_id, prompt_data in data.items():
        # Support two formats:
        # Format A: simple_greeting: "Hello!"
        # Format B: user_greeting: {template: "Hello {name}!", description: "..."}
        # Format C: user_greeting: {versions: {v1: {...}, v2: {...}}}

        if isinstance(prompt_data, str):
            # Format A: Direct string
            result[prompt_id] = {
                "template": prompt_data,
                "description": "",
            }
        elif isinstance(prompt_data, dict):
            # Format B/C: Dictionary with template and/or versions
            if "template" not in prompt_data and "versions" not in prompt_data:
                raise ValueError(f"Missing 'template' field for prompt '{prompt_id}'")

            entry = {}
            if "template" in prompt_data:
                entry["template"] = prompt_data["template"]
            if "description" in prompt_data:
                entry["description"] = prompt_data["description"]
            if "versions" in prompt_data:
                entry["versions"] = prompt_data["versions"]

            result[prompt_id] = entry
        else:
            raise ValueError(f"Invalid format for prompt '{prompt_id}': expected a string or dictionary")

    return result


def save_prompts_file(path: Path, prompts: dict[str, dict]) -> None:
    """
    Save all prompts to a single prompts.yaml file.
    
    Args:
        path: Path to save the prompts.yaml file
        prompts: Dictionary mapping prompt IDs to their data (template, description)
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Format data for YAML output
    data = {}
    for prompt_id, prompt_data in prompts.items():
        entry = {}

        if "description" in prompt_data:
            entry["description"] = prompt_data.get("description", "")

        if "template" in prompt_data:
            entry["template"] = prompt_data.get("template", "")

        if "versions" in prompt_data:
            entry["versions"] = prompt_data["versions"]

        data[prompt_id] = entry
    
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

