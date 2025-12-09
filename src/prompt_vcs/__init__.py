"""
prompt-vcs: Git-native prompt management library for LLM applications.
"""

from prompt_vcs.api import p, prompt
from prompt_vcs.manager import PromptManager, get_manager

__version__ = "0.2.1"
__all__ = ["p", "prompt", "PromptManager", "get_manager"]
