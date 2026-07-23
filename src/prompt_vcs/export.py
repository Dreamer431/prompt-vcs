"""
Export prompts to various formats (JSON, OpenAI messages, LangChain PromptTemplate).
"""

import json
import re
from typing import Any


def _extract_variables(template: str) -> list[str]:
    """Return sorted unique variable names found in *template*.

    Recognises both simple ``{name}`` placeholders and Jinja2 ``{{ name }}``
    expressions.  Format-spec and conversion suffixes are stripped so that
    ``{value:.2f}`` yields ``"value"``.
    """
    # Simple {var}, {var:spec}, {var!conv} – but not {{ }}
    simple = re.findall(r"(?<!\{)\{([a-zA-Z_]\w*)(?:[!:][^{}]*)?\}(?!\})", template)
    # Jinja2 {{ var }} (possibly with filters)
    jinja = re.findall(r"\{\{\s*([a-zA-Z_]\w*)[\s|]", template)
    return sorted(set(simple + jinja))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_prompts(entries: list[dict[str, Any]], fmt: str) -> str:
    """Serialise *entries* to the requested *fmt* string.

    Parameters
    ----------
    entries:
        List of dicts with at least the keys ``id`` and ``template``.
        Optional keys: ``description``, ``locked``, ``versions``.
    fmt:
        One of ``"json"``, ``"openai"``, or ``"langchain"``.

    Returns
    -------
    str
        UTF-8 JSON string.

    Raises
    ------
    ValueError
        If *fmt* is not supported.
    """
    if fmt == "json":
        return _export_json(entries)
    if fmt == "openai":
        return _export_openai(entries)
    if fmt == "langchain":
        return _export_langchain(entries)
    raise ValueError(
        f"Unknown format: {fmt!r}. Supported formats: json, openai, langchain"
    )


# ---------------------------------------------------------------------------
# Format implementations
# ---------------------------------------------------------------------------

def _export_json(entries: list[dict[str, Any]]) -> str:
    """Plain JSON – one object per prompt preserving all metadata."""
    return json.dumps(entries, ensure_ascii=False, indent=2)


def _export_openai(entries: list[dict[str, Any]]) -> str:
    """OpenAI *Chat Completions* ``messages`` format.

    Each prompt is represented as a ``messages`` array whose sole element is a
    ``system`` turn containing the raw template string.  Variable names
    extracted from the template are listed separately so callers know which
    keys to substitute before sending to the API.

    Example output::

        {
          "greeting": {
            "description": "...",
            "messages": [{"role": "system", "content": "Hello {name}!"}],
            "variables": ["name"],
            "locked_version": "v2"
          }
        }
    """
    result: dict[str, Any] = {}
    for entry in entries:
        prompt_id = entry["id"]
        template = entry.get("template", "")
        record: dict[str, Any] = {
            "description": entry.get("description", ""),
            "messages": [{"role": "system", "content": template}],
            "variables": _extract_variables(template),
        }
        if entry.get("locked"):
            record["locked_version"] = entry["locked"]
        if entry.get("versions"):
            record["available_versions"] = entry["versions"]
        result[prompt_id] = record
    return json.dumps(result, ensure_ascii=False, indent=2)


def _export_langchain(entries: list[dict[str, Any]]) -> str:
    """LangChain ``PromptTemplate`` serialisation format.

    Produces a dict keyed by prompt ID.  Each value follows the schema that
    ``PromptTemplate.from_template`` would produce when serialised with
    ``langchain.load.dump.dumpd()``.

    Example output::

        {
          "greeting": {
            "_type": "prompt",
            "input_variables": ["name"],
            "template": "Hello {name}!",
            "template_format": "f-string"
          }
        }
    """
    result: dict[str, Any] = {}
    for entry in entries:
        prompt_id = entry["id"]
        template = entry.get("template", "")
        record: dict[str, Any] = {
            "_type": "prompt",
            "input_variables": _extract_variables(template),
            "template": template,
            "template_format": "f-string",
        }
        description = entry.get("description", "")
        if description:
            record["description"] = description
        if entry.get("locked"):
            record["locked_version"] = entry["locked"]
        result[prompt_id] = record
    return json.dumps(result, ensure_ascii=False, indent=2)
