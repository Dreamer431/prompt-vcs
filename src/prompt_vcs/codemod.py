"""
LibCST-based code migration tool for converting hardcoded prompts to p() calls.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import libcst as cst

from libcst.codemod import CodemodContext
from libcst.codemod.visitors import AddImportsVisitor


# Default variable name patterns that indicate a prompt
DEFAULT_PROMPT_VAR_PATTERNS = ["prompt", "template", "instruction", "msg"]

# Minimum string length to consider for migration
MIN_STRING_LENGTH = 10


@dataclass
class MigrationCandidate:
    """Represents a potential migration target."""
    variable_name: str
    original_code: str
    new_code: str
    line_number: int
    prompt_id: str


@dataclass
class FStringPart:
    """Represents a part of an f-string."""
    placeholder: str  # The placeholder name in the template (e.g., "user_name")
    expression: str   # The original expression (e.g., "user.name")
    format_spec: str  # Format specification (e.g., ":.2f")


def sanitize_variable_name(expr: str) -> str:
    """
    Sanitize an expression to create a valid Python identifier.
    
    Examples:
        user.name -> user_name
        data['score'] -> data_score
        items[0] -> items_0
        x + 1 -> None (too complex, return original with underscores)
    """
    # Replace attribute access (.)
    result = expr.replace(".", "_")
    
    # Replace string index access ['key'] or ["key"]
    result = re.sub(r"\['([^']+)'\]", r"_\1", result)
    result = re.sub(r'\["([^"]+)"\]', r"_\1", result)
    
    # Replace numeric index access [0], [1], etc.
    result = re.sub(r"\[(\d+)\]", r"_\1", result)
    
    # Remove any remaining brackets
    result = re.sub(r"[\[\]]", "_", result)
    
    # Replace any non-identifier characters with underscore
    result = re.sub(r"[^a-zA-Z0-9_]", "_", result)
    
    # Remove leading/trailing underscores and collapse multiple underscores
    result = re.sub(r"_+", "_", result).strip("_")
    
    # Ensure it starts with a letter or underscore
    if result and result[0].isdigit():
        result = "_" + result
    
    return result or "arg"


def is_complex_expression(expr: str) -> bool:
    """
    Check if an expression is too complex to migrate safely.
    
    Complex expressions include function calls, operators, etc.
    """
    # Check for function calls
    if re.search(r"\w+\s*\(", expr):
        return True
    
    # Check for operators (but allow attribute/index access)
    operators = ["+", "-", "*", "/", "%", "==", "!=", "<", ">", " and ", " or ", " not "]
    for op in operators:
        if op in expr:
            return True
    
    return False


class FStringExtractor(cst.CSTVisitor):
    """Extract parts from a FormattedString (f-string)."""
    
    def __init__(self) -> None:
        self.parts: list[FStringPart] = []
        self.has_complex_expression = False
        self.template_parts: list[str] = []
    
    def visit_FormattedStringText(self, node: cst.FormattedStringText) -> None:
        """Visit literal text parts of the f-string."""
        self.template_parts.append(node.value)
    
    def visit_FormattedStringExpression(self, node: cst.FormattedStringExpression) -> None:
        """Visit expression parts of the f-string."""
        # Get the expression code
        expr_code = cst.parse_module("").code_for_node(node.expression)
        
        # Check for complex expressions
        if is_complex_expression(expr_code):
            self.has_complex_expression = True
            return
        
        # Get format specification if present
        format_spec = ""
        if node.format_spec:
            # Format spec is a sequence of FormattedStringContent
            for part in node.format_spec:
                if isinstance(part, cst.FormattedStringText):
                    format_spec += part.value
        
        # Include conversion (e.g., !r, !s, !a)
        conversion = ""
        if node.conversion:
            conversion = f"!{node.conversion}"
        
        # Create placeholder name
        placeholder = sanitize_variable_name(expr_code)
        
        # Build the template placeholder with format spec
        full_placeholder = f"{{{placeholder}{conversion}{format_spec}}}"
        self.template_parts.append(full_placeholder)
        
        self.parts.append(FStringPart(
            placeholder=placeholder,
            expression=expr_code,
            format_spec=conversion + format_spec,
        ))


def extract_fstring_parts(fstring: cst.FormattedString) -> tuple[str, list[FStringPart], bool]:
    """
    Extract template string and variable parts from an f-string.
    
    Returns:
        Tuple of (template_string, parts, has_complex_expression)
    """
    parts_list: list[FStringPart] = []
    template_parts: list[str] = []
    has_complex_expression = False
    
    # Directly iterate over fstring.parts instead of using walk()
    for part in fstring.parts:
        if isinstance(part, cst.FormattedStringText):
            # Literal text part
            template_parts.append(part.value)
        elif isinstance(part, cst.FormattedStringExpression):
            # Expression part
            # Get the expression code
            expr_code = cst.parse_module("").code_for_node(part.expression)
            
            # Check for complex expressions
            if is_complex_expression(expr_code):
                has_complex_expression = True
                # Still add a placeholder for display purposes
                template_parts.append(f"{{{expr_code}}}")
                continue
            
            # Get format specification if present
            format_spec = ""
            if part.format_spec:
                # Format spec is a sequence of FormattedStringContent
                for spec_part in part.format_spec:
                    if isinstance(spec_part, cst.FormattedStringText):
                        format_spec = ":" + spec_part.value
            
            # Include conversion (e.g., !r, !s, !a)
            conversion = ""
            if part.conversion:
                conversion = f"!{part.conversion}"
            
            # Create placeholder name
            placeholder = sanitize_variable_name(expr_code)
            
            # Build the template placeholder with format spec
            full_placeholder = f"{{{placeholder}{conversion}{format_spec}}}"
            template_parts.append(full_placeholder)
            
            parts_list.append(FStringPart(
                placeholder=placeholder,
                expression=expr_code,
                format_spec=conversion + format_spec,
            ))
    
    template = "".join(template_parts)
    return template, parts_list, has_complex_expression


def get_string_content(node: cst.BaseExpression) -> Optional[str]:
    """Extract string content from a SimpleString or ConcatenatedString."""
    if isinstance(node, cst.SimpleString):
        # Remove quotes and get raw content
        value = node.value
        # Handle different quote styles
        if value.startswith('"""') or value.startswith("'''"):
            return value[3:-3]
        elif value.startswith('"') or value.startswith("'"):
            return value[1:-1]
    elif isinstance(node, cst.ConcatenatedString):
        # Handle concatenated strings
        parts = []
        for part in node.left, node.right:
            content = get_string_content(part)
            if content:
                parts.append(content)
        return "".join(parts) if parts else None
    return None


class PromptMigrator(cst.CSTTransformer):
    """
    LibCST Transformer that converts hardcoded prompt strings to p() calls.
    """
    
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    
    def __init__(
        self,
        filename: str,
        clean_mode: bool = False,
        project_root: Optional[Path] = None,
        extra_patterns: Optional[list[str]] = None,
    ) -> None:
        super().__init__()
        self.filename = Path(filename).stem
        self.candidates: list[MigrationCandidate] = []
        self.needs_import = False
        self._used_ids: set[str] = set()
        self.clean_mode = clean_mode
        self.project_root = project_root
        self._written_yamls: list[Path] = []  # Track written YAML files
        self._single_file_mode: bool = False  # Whether to use single-file mode
        self._pending_prompts: dict[str, dict] = {}  # Prompts to write in single-file mode
        
        # Build list of patterns to match
        self._patterns = list(DEFAULT_PROMPT_VAR_PATTERNS)
        if extra_patterns:
            self._patterns.extend(extra_patterns)
        
        # Detect single-file vs multi-file mode
        if project_root:
            prompts_yaml = project_root / "prompts.yaml"
            if prompts_yaml.exists():
                self._single_file_mode = True
    
    def _is_target_variable(self, targets: Sequence[cst.BaseAssignTargetExpression]) -> Optional[str]:
        """Check if any target variable name matches our patterns."""
        for target in targets:
            if isinstance(target, cst.AssignTarget):
                target = target.target
            
            if isinstance(target, cst.Name):
                name_lower = target.value.lower()
                for pattern in self._patterns:
                    if pattern.lower() in name_lower:
                        return target.value
        return None
    
    def _generate_prompt_id(self, var_name: str) -> str:
        """Generate a unique prompt ID based on filename and variable name."""
        base_id = f"{self.filename}_{var_name}"
        
        # Ensure uniqueness
        if base_id not in self._used_ids:
            self._used_ids.add(base_id)
            return base_id
        
        counter = 2
        while f"{base_id}_{counter}" in self._used_ids:
            counter += 1
        
        unique_id = f"{base_id}_{counter}"
        self._used_ids.add(unique_id)
        return unique_id
    
    def _build_p_call(
        self,
        prompt_id: str,
        template: str,
        kwargs: list[FStringPart],
        original_quotes: str = '"""',
        include_default: bool = True,
    ) -> cst.Call:
        """
        Build a p() function call node.
        
        Args:
            prompt_id: The prompt ID string
            template: The template content
            kwargs: List of variable parts to include as keyword arguments
            original_quotes: Quote style hint from original code
            include_default: If True, include template as second argument.
                           If False, only include prompt_id and kwargs (clean mode).
        """
        # Build kwargs
        kwarg_nodes = []
        seen_placeholders: set[str] = set()
        
        for part in kwargs:
            # Skip duplicate placeholders
            if part.placeholder in seen_placeholders:
                continue
            seen_placeholders.add(part.placeholder)
            
            # Parse the original expression
            try:
                expr = cst.parse_expression(part.expression)
            except Exception:
                # If parsing fails, use the expression as a name
                expr = cst.Name(part.expression)
            
            kwarg_nodes.append(cst.Arg(
                keyword=cst.Name(part.placeholder),
                value=expr,
                equal=cst.AssignEqual(
                    whitespace_before=cst.SimpleWhitespace(""),
                    whitespace_after=cst.SimpleWhitespace(""),
                ),
            ))
        
        # Build the p() call
        args = [
            cst.Arg(value=cst.SimpleString(f'"{prompt_id}"')),
        ]
        
        # Include template as second argument only if not in clean mode
        if include_default:
            # Determine quote style for the template
            if '"""' in template:
                quote = "'''"
            elif "'''" in template:
                quote = '"""'
            elif "\n" in template:
                quote = '"""'
            elif '"' in template and "'" not in template:
                quote = "'"
            else:
                quote = '"'
            
            template_str = cst.SimpleString(f'{quote}{template}{quote}')
            args.append(cst.Arg(value=template_str))
        
        args.extend(kwarg_nodes)
        
        return cst.Call(
            func=cst.Name("p"),
            args=args,
        )
    
    def _write_yaml_if_needed(self, prompt_id: str, template: str) -> Optional[Path]:
        """
        Write the template to a YAML file if in clean_mode.
        
        In single-file mode (prompts.yaml exists), prompts are collected in
        _pending_prompts and written together at the end via flush_pending_prompts().
        
        In multi-file mode, creates prompts/{id}/v1.yaml immediately.
        
        Returns:
            Path to the written YAML file, or None if skipped/not applicable
        """
        if not self.clean_mode:
            return None
        
        if self.project_root is None:
            # Cannot write without project root
            return None
        
        if self._single_file_mode:
            # Single-file mode: collect prompts for batch writing
            from prompt_vcs.templates import load_prompts_file
            
            prompts_yaml_path = self.project_root / "prompts.yaml"
            
            # Load existing prompts to check for duplicates
            try:
                existing_prompts = load_prompts_file(prompts_yaml_path)
            except Exception:
                existing_prompts = {}
            
            # Skip if prompt already exists
            if prompt_id in existing_prompts or prompt_id in self._pending_prompts:
                self._written_yamls.append(prompts_yaml_path)
                return None  # Signal that we skipped
            
            # Add to pending prompts
            self._pending_prompts[prompt_id] = {
                "description": f"Auto-generated from {self.filename}",
                "template": template,
            }
            
            self._written_yamls.append(prompts_yaml_path)
            return prompts_yaml_path
        else:
            # Multi-file mode: create prompts/{id}/v1.yaml
            from prompt_vcs.templates import save_yaml_template
            
            yaml_path = self.project_root / "prompts" / prompt_id / "v1.yaml"
            
            # Skip if file already exists (don't overwrite)
            if yaml_path.exists():
                self._written_yamls.append(yaml_path)  # Track for reporting
                return None  # Signal that we skipped
            
            # Write the YAML file
            save_yaml_template(
                yaml_path,
                template=template,
                version="v1",
                description=f"Auto-generated from {self.filename}",
            )
            
            self._written_yamls.append(yaml_path)
            return yaml_path
    
    def flush_pending_prompts(self) -> int:
        """
        Write all pending prompts to prompts.yaml (single-file mode only).
        
        Returns:
            Number of prompts written
        """
        if not self._single_file_mode or not self._pending_prompts:
            return 0
        
        if self.project_root is None:
            return 0
        
        from prompt_vcs.templates import load_prompts_file, save_prompts_file
        
        prompts_yaml_path = self.project_root / "prompts.yaml"
        
        # Load existing prompts
        try:
            existing_prompts = load_prompts_file(prompts_yaml_path)
        except Exception:
            existing_prompts = {}
        
        # Merge with pending prompts
        merged_prompts = {**existing_prompts, **self._pending_prompts}
        
        # Write back to file
        save_prompts_file(prompts_yaml_path, merged_prompts)
        
        count = len(self._pending_prompts)
        self._pending_prompts.clear()
        return count
    
    def leave_Assign(
        self,
        original_node: cst.Assign,
        updated_node: cst.Assign,
    ) -> cst.Assign:
        """Transform assignment statements with prompt strings."""
        # Check if this is a target variable
        var_name = self._is_target_variable(original_node.targets)
        if not var_name:
            return updated_node
        
        value = original_node.value
        
        # Handle FormattedString (f-string)
        if isinstance(value, cst.FormattedString):
            template, parts, has_complex = extract_fstring_parts(value)
            
            # Skip complex expressions
            if has_complex:
                return updated_node
            
            # Check minimum length
            if len(template) <= MIN_STRING_LENGTH:
                return updated_node
            
            # Generate prompt ID
            prompt_id = self._generate_prompt_id(var_name)
            
            # In clean_mode, write YAML and generate p() without default
            if self.clean_mode:
                self._write_yaml_if_needed(prompt_id, template)
                new_call = self._build_p_call(prompt_id, template, parts, include_default=False)
            else:
                new_call = self._build_p_call(prompt_id, template, parts)
            
            # Record the candidate
            original_code = cst.parse_module("").code_for_node(original_node)
            new_node = updated_node.with_changes(value=new_call)
            new_code = cst.parse_module("").code_for_node(new_node)
            
            # Get line number
            pos = self.get_metadata(cst.metadata.PositionProvider, original_node, None)
            line_number = pos.start.line if pos else 0
            
            self.candidates.append(MigrationCandidate(
                variable_name=var_name,
                original_code=original_code,
                new_code=new_code,
                line_number=line_number,
                prompt_id=prompt_id,
            ))
            
            self.needs_import = True
            return new_node
        
        # Handle SimpleString
        elif isinstance(value, cst.SimpleString):
            content = get_string_content(value)
            if content is None or len(content) <= MIN_STRING_LENGTH:
                return updated_node
            
            # Generate prompt ID
            prompt_id = self._generate_prompt_id(var_name)
            
            # In clean_mode, write YAML and generate p() without default
            if self.clean_mode:
                self._write_yaml_if_needed(prompt_id, content)
                new_call = self._build_p_call(prompt_id, content, [], include_default=False)
            else:
                new_call = self._build_p_call(prompt_id, content, [])
            
            # Record the candidate
            original_code = cst.parse_module("").code_for_node(original_node)
            new_node = updated_node.with_changes(value=new_call)
            new_code = cst.parse_module("").code_for_node(new_node)
            
            pos = self.get_metadata(cst.metadata.PositionProvider, original_node, None)
            line_number = pos.start.line if pos else 0
            
            self.candidates.append(MigrationCandidate(
                variable_name=var_name,
                original_code=original_code,
                new_code=new_code,
                line_number=line_number,
                prompt_id=prompt_id,
            ))
            
            self.needs_import = True
            return new_node
        
        # Handle ConcatenatedString (multi-line strings)
        elif isinstance(value, cst.ConcatenatedString):
            content = get_string_content(value)
            if content is None or len(content) <= MIN_STRING_LENGTH:
                return updated_node
            
            prompt_id = self._generate_prompt_id(var_name)
            
            # In clean_mode, write YAML and generate p() without default
            if self.clean_mode:
                self._write_yaml_if_needed(prompt_id, content)
                new_call = self._build_p_call(prompt_id, content, [], include_default=False)
            else:
                new_call = self._build_p_call(prompt_id, content, [])
            
            original_code = cst.parse_module("").code_for_node(original_node)
            new_node = updated_node.with_changes(value=new_call)
            new_code = cst.parse_module("").code_for_node(new_node)
            
            pos = self.get_metadata(cst.metadata.PositionProvider, original_node, None)
            line_number = pos.start.line if pos else 0
            
            self.candidates.append(MigrationCandidate(
                variable_name=var_name,
                original_code=original_code,
                new_code=new_code,
                line_number=line_number,
                prompt_id=prompt_id,
            ))
            
            self.needs_import = True
            return new_node
        
        return updated_node


def add_import_if_needed(tree: cst.Module, needs_import: bool) -> cst.Module:
    """Add 'from prompt_vcs import p' if needed, handling __future__ imports correctly."""
    if not needs_import:
        return tree
    
    # Use AddImportsVisitor for safe import insertion
    context = CodemodContext()
    AddImportsVisitor.add_needed_import(context, "prompt_vcs", "p")
    
    # Apply the import visitor - use transform_module instead of transform
    visitor = AddImportsVisitor(context)
    modified_tree = tree.visit(visitor)
    return modified_tree


def migrate_file_content(
    content: str,
    filename: str,
    apply_changes: bool = False,
    clean_mode: bool = False,
    project_root: Optional[Path] = None,
    extra_patterns: Optional[list[str]] = None,
) -> tuple[str, list[MigrationCandidate]]:
    """
    Migrate prompt strings in file content.
    
    Args:
        content: The file content
        filename: The filename (used for generating IDs)
        apply_changes: Whether to apply the changes
        clean_mode: If True, write prompts to YAML and generate p() without default
        project_root: Project root directory for writing YAML files (required for clean_mode)
        extra_patterns: Additional variable name patterns to match
        
    Returns:
        Tuple of (modified_content, candidates)
    """
    # Parse the module with metadata
    wrapper = cst.metadata.MetadataWrapper(cst.parse_module(content))
    
    # Create and run the migrator
    migrator = PromptMigrator(
        filename,
        clean_mode=clean_mode,
        project_root=project_root,
        extra_patterns=extra_patterns,
    )
    
    if apply_changes:
        # Actually apply the transformation
        modified_tree = wrapper.visit(migrator)
        
        # Add import if needed
        if migrator.needs_import:
            modified_tree = add_import_if_needed(modified_tree, True)
        
        # In clean mode with single-file, flush pending prompts to prompts.yaml
        if clean_mode:
            migrator.flush_pending_prompts()
        
        return modified_tree.code, migrator.candidates
    else:
        # Just collect candidates without modifying
        wrapper.visit(migrator)
        return content, migrator.candidates


def migrate_file(
    file_path: Path,
    dry_run: bool = True,
    clean_mode: bool = False,
    project_root: Optional[Path] = None,
) -> list[MigrationCandidate]:
    """
    Migrate a single Python file.
    
    Args:
        file_path: Path to the Python file
        dry_run: If True, don't actually modify the file
        clean_mode: If True, write prompts to YAML and generate p() without default
        project_root: Project root directory for writing YAML files (required for clean_mode)
        
    Returns:
        List of migration candidates
    """
    content = file_path.read_text(encoding="utf-8")
    
    modified_content, candidates = migrate_file_content(
        content,
        file_path.name,
        apply_changes=not dry_run,
        clean_mode=clean_mode,
        project_root=project_root,
    )
    
    if not dry_run and candidates:
        file_path.write_text(modified_content, encoding="utf-8")
    
    return candidates

