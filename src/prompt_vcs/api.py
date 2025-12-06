"""
Public API: p() function and @prompt decorator.
"""

import functools
import inspect
import textwrap
from typing import Any, Callable, Optional, TypeVar

from prompt_vcs.manager import get_manager, PromptDefinition


F = TypeVar("F", bound=Callable[..., Any])


class PromptNotFoundError(ValueError):
    """Raised when a prompt cannot be found and no default content is provided."""
    pass


def p(prompt_id: str, default_content: Optional[str] = None, **kwargs: Any) -> str:
    """
    Inline mode: Get a prompt with optional version locking.
    
    This function provides a low-friction way to manage prompts. By default,
    it returns the rendered default_content. When a lockfile specifies a
    version for this prompt_id, it loads and renders that version instead.
    
    Usage:
        # With default content (inline mode):
        msg = p("user_greeting", "你好 {name}", name="开发者")
        
        # Without default content (clean mode, requires YAML file):
        msg = p("user_greeting", name="开发者")
    
    IMPORTANT: Do NOT use f-strings as default_content. Use templated strings:
        WRONG:  p("id", f"Hello {name}")      # Variable rendered too early
        RIGHT:  p("id", "Hello {name}", name=name)  # Variable passed as kwarg
    
    Args:
        prompt_id: Unique identifier for this prompt
        default_content: Optional default template string (with {variable} placeholders).
                        If None, the prompt must exist in lockfile or prompts directory.
        **kwargs: Variables to substitute in the template
        
    Returns:
        Rendered prompt string
        
    Raises:
        PromptNotFoundError: If prompt is not found and no default_content is provided
    """
    manager = get_manager()
    
    # Register this prompt definition if default_content is provided
    if default_content is not None:
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            source_file = caller_frame.f_code.co_filename if caller_frame else ""
            line_number = caller_frame.f_lineno if caller_frame else 0
        finally:
            del frame
        
        definition = PromptDefinition(
            id=prompt_id,
            default_content=default_content,
            source_file=source_file,
            line_number=line_number,
        )
        manager.register_prompt(definition)
    
    return manager.get_prompt(prompt_id, default_content, **kwargs)


def prompt(
    id: str,
    default_version: str = "v1",
) -> Callable[[F], F]:
    """
    Decorator mode: Use function docstring as prompt template.
    
    This decorator allows structured prompt management for complex prompts.
    The function's docstring serves as the default template source.
    
    Usage:
        @prompt(id="system_core", default_version="v1")
        def get_system_prompt(role: str):
            '''
            你是一个乐于助人的助手，扮演的角色是 {role}。
            '''
            pass
        
        result = get_system_prompt(role="translator")
    
    Args:
        id: Unique identifier for this prompt
        default_version: Default version to use (informational)
        
    Returns:
        Decorator function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            manager = get_manager()
            
            # Get the docstring as default template
            docstring = func.__doc__ or ""
            # Dedent and strip the docstring
            default_content = textwrap.dedent(docstring).strip()
            
            # Register this prompt definition
            source_file = inspect.getfile(func)
            try:
                line_number = inspect.getsourcelines(func)[1]
            except OSError:
                line_number = 0
            
            definition = PromptDefinition(
                id=id,
                default_content=default_content,
                source_file=source_file,
                line_number=line_number,
            )
            manager.register_prompt(definition)
            
            # Bind positional args to their parameter names
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            return manager.get_prompt(id, default_content, **bound.arguments)
        
        return wrapper  # type: ignore
    
    return decorator
