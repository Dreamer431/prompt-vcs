"""
AST-based prompt extractor: scans Python code for p() calls and @prompt decorators.
"""

import ast
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class ExtractedPrompt:
    """Represents a prompt extracted from source code."""
    id: str
    default_content: str
    source_file: str
    line_number: int
    is_decorator: bool = False


class PromptIdConflictError(Exception):
    """Raised when the same prompt ID is defined with different content."""
    
    def __init__(self, prompt_id: str, locations: list[tuple[str, int, str]]):
        self.prompt_id = prompt_id
        self.locations = locations
        
        message = f"Prompt ID '{prompt_id}' is defined with different content in multiple locations:\n"
        for file, line, content in locations:
            preview = content[:50] + "..." if len(content) > 50 else content
            message += f"  - {file}:{line}: {repr(preview)}\n"
        
        super().__init__(message)


class PromptExtractor(ast.NodeVisitor):
    """
    AST visitor that extracts prompt definitions from Python source code.
    
    Extracts:
    1. p("id", "content") function calls
    2. @prompt(id="...") decorator usages
    
    Warnings are issued for:
    - f-strings or non-static strings as p() second argument
    """
    
    def __init__(self, source_file: str):
        self.source_file = source_file
        self.prompts: list[ExtractedPrompt] = []
        self._current_decorators: list[ast.expr] = []
    
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to find p() invocations."""
        # Check if this is a call to p()
        if isinstance(node.func, ast.Name) and node.func.id == "p":
            self._extract_p_call(node)
        
        # Continue visiting children
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to find @prompt decorators."""
        for decorator in node.decorator_list:
            self._check_prompt_decorator(decorator, node)
        
        # Continue visiting children
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions for @prompt decorators."""
        for decorator in node.decorator_list:
            self._check_prompt_decorator(decorator, node)
        
        self.generic_visit(node)
    
    def _extract_p_call(self, node: ast.Call) -> None:
        """Extract prompt definition from a p() call."""
        if len(node.args) < 2:
            return
        
        # First argument: prompt ID (must be a string)
        id_arg = node.args[0]
        if not isinstance(id_arg, ast.Constant) or not isinstance(id_arg.value, str):
            warnings.warn(
                f"{self.source_file}:{node.lineno}: p() first argument must be a static string",
                SyntaxWarning,
            )
            return
        
        prompt_id = id_arg.value
        
        # Second argument: default content (must be a static string)
        content_arg = node.args[1]
        
        # Check for f-strings (JoinedStr in AST)
        if isinstance(content_arg, ast.JoinedStr):
            warnings.warn(
                f"{self.source_file}:{node.lineno}: p() does not support f-strings. "
                f"Use p(\"{prompt_id}\", \"template {{var}}\", var=value) instead.",
                SyntaxWarning,
            )
            return
        
        # Check for non-static strings (variables, function calls, etc.)
        if not isinstance(content_arg, ast.Constant) or not isinstance(content_arg.value, str):
            warnings.warn(
                f"{self.source_file}:{node.lineno}: p() second argument must be a static string. "
                f"Skipping prompt '{prompt_id}'.",
                SyntaxWarning,
            )
            return
        
        default_content = content_arg.value
        
        self.prompts.append(ExtractedPrompt(
            id=prompt_id,
            default_content=default_content,
            source_file=self.source_file,
            line_number=node.lineno,
            is_decorator=False,
        ))
    
    def _check_prompt_decorator(
        self,
        decorator: ast.expr,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Check if a decorator is @prompt and extract its definition."""
        # Handle @prompt(id="...") 
        if isinstance(decorator, ast.Call):
            func_node = decorator.func
            
            # Check for @prompt(...) or @module.prompt(...)
            is_prompt = False
            if isinstance(func_node, ast.Name) and func_node.id == "prompt":
                is_prompt = True
            elif isinstance(func_node, ast.Attribute) and func_node.attr == "prompt":
                is_prompt = True
            
            if not is_prompt:
                return
            
            # Find the id keyword argument
            prompt_id = None
            for keyword in decorator.keywords:
                if keyword.arg == "id":
                    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        prompt_id = keyword.value.value
                    break
            
            if prompt_id is None:
                return
            
            # Get docstring as default content
            docstring = ast.get_docstring(func) or ""
            
            self.prompts.append(ExtractedPrompt(
                id=prompt_id,
                default_content=docstring,
                source_file=self.source_file,
                line_number=func.lineno,
                is_decorator=True,
            ))


def extract_prompts_from_file(file_path: Path) -> list[ExtractedPrompt]:
    """
    Extract all prompt definitions from a Python file.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        List of extracted prompts
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except (IOError, UnicodeDecodeError) as e:
        warnings.warn(f"Could not read {file_path}: {e}")
        return []
    
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        warnings.warn(f"Syntax error in {file_path}: {e}")
        return []
    
    extractor = PromptExtractor(str(file_path))
    extractor.visit(tree)
    
    return extractor.prompts


def extract_prompts_from_directory(
    directory: Path,
    recursive: bool = True,
) -> Iterator[ExtractedPrompt]:
    """
    Extract all prompt definitions from Python files in a directory.
    
    Args:
        directory: Path to the directory
        recursive: Whether to search recursively
        
    Yields:
        Extracted prompts
    """
    pattern = "**/*.py" if recursive else "*.py"
    
    for py_file in directory.glob(pattern):
        yield from extract_prompts_from_file(py_file)


def check_id_conflicts(prompts: list[ExtractedPrompt]) -> None:
    """
    Check for prompt ID conflicts (same ID with different content).
    
    Args:
        prompts: List of extracted prompts
        
    Raises:
        PromptIdConflictError: If conflicts are found
    """
    # Group by ID
    by_id: dict[str, list[ExtractedPrompt]] = {}
    for prompt in prompts:
        if prompt.id not in by_id:
            by_id[prompt.id] = []
        by_id[prompt.id].append(prompt)
    
    # Check for conflicts
    for prompt_id, group in by_id.items():
        if len(group) <= 1:
            continue
        
        # Check if all have the same content
        contents = set(p.default_content for p in group)
        if len(contents) > 1:
            locations = [
                (p.source_file, p.line_number, p.default_content)
                for p in group
            ]
            raise PromptIdConflictError(prompt_id, locations)
