"""
CLI tool for prompt-vcs (pvcs).
"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from prompt_vcs.extractor import (
    extract_prompts_from_directory,
    check_id_conflicts,
    PromptIdConflictError,
)
from prompt_vcs.manager import LOCKFILE_NAME, PROMPTS_DIR, PROMPTS_FILE
from prompt_vcs.templates import save_yaml_template, save_prompts_file, load_prompts_file


app = typer.Typer(
    name="pvcs",
    help="Git-native prompt management CLI",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project root path (defaults to current directory)",
    ),
    split: bool = typer.Option(
        False,
        "--split",
        help="Use multi-file mode (prompts/ directory) instead of single-file mode",
    ),
) -> None:
    """
    Initialize a new prompt-vcs project.
    
    Creates:
    - .prompt_lock.json: Version lockfile
    - prompts.yaml: Single-file prompt storage (default)
    - OR prompts/: Directory for prompt YAML files (with --split)
    """
    project_root = (path or Path.cwd()).resolve()
    
    lockfile_path = project_root / LOCKFILE_NAME
    prompts_file = project_root / PROMPTS_FILE
    prompts_dir = project_root / PROMPTS_DIR
    
    # Create lockfile if not exists
    if not lockfile_path.exists():
        with open(lockfile_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
        console.print(f"[green]✓[/green] Created {lockfile_path.name}")
    else:
        console.print(f"[yellow]![/yellow] {lockfile_path.name} already exists")
    
    if split:
        # Multi-file mode: create prompts/ directory
        if not prompts_dir.exists():
            prompts_dir.mkdir(parents=True)
            console.print(f"[green]✓[/green] Created {prompts_dir.name}/ directory (multi-file mode)")
        else:
            console.print(f"[yellow]![/yellow] {prompts_dir.name}/ already exists")
    else:
        # Single-file mode (default): create prompts.yaml
        if not prompts_file.exists():
            # Create empty prompts.yaml with example comment
            prompts_file.write_text(
                "# Prompt definitions for prompt-vcs\n"
                "# Format:\n"
                "#   prompt_id:\n"
                "#     description: \"Description of the prompt\"\n"
                "#     template: |\n"
                "#       Your prompt template with {variables}\n"
                "\n",
                encoding="utf-8"
            )
            console.print(f"[green]✓[/green] Created {prompts_file.name} (single-file mode)")
        else:
            console.print(f"[yellow]![/yellow] {prompts_file.name} already exists")
    
    console.print("\n[bold green]Project initialized successfully![/bold green]")


@app.command()
def scaffold(
    src_dir: Path = typer.Argument(
        ...,
        help="Source directory to scan for prompts",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for YAML files (multi-file mode only)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run", "-n",
        help="Show what would be created without actually creating files",
    ),
) -> None:
    """
    Scan source code and generate YAML files for discovered prompts.
    
    Automatically detects mode:
    - If prompts.yaml exists: append to single file
    - If prompts/ directory exists: create separate files per prompt
    
    Uses AST parsing to find:
    - p("id", "content") function calls
    - @prompt(id="...") decorator usages
    """
    src_path = src_dir.resolve()
    
    if not src_path.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src_path}")
        raise typer.Exit(1)
    
    # Find project root
    project_root: Optional[Path] = None
    current = src_path
    while current != current.parent:
        if (current / LOCKFILE_NAME).exists() or (current / ".git").exists():
            project_root = current
            break
        current = current.parent
    
    if project_root is None:
        project_root = Path.cwd()
    
    # Detect mode: single-file (prompts.yaml) or multi-file (prompts/)
    prompts_file = project_root / PROMPTS_FILE
    prompts_dir = output_dir.resolve() if output_dir else project_root / PROMPTS_DIR
    
    use_single_file = prompts_file.exists() and not output_dir
    
    if use_single_file:
        console.print("[blue]Mode:[/blue] Single-file (prompts.yaml)")
        console.print(f"[blue]Scanning:[/blue] {src_path}")
        console.print(f"[blue]Output:[/blue] {prompts_file}\n")
    else:
        console.print("[blue]Mode:[/blue] Multi-file (prompts/)")
        console.print(f"[blue]Scanning:[/blue] {src_path}")
        console.print(f"[blue]Output:[/blue] {prompts_dir}\n")
    
    # Extract prompts
    prompts = list(extract_prompts_from_directory(src_path))
    
    if not prompts:
        console.print("[yellow]No prompts found in source code.[/yellow]")
        return
    
    # Check for ID conflicts
    try:
        check_id_conflicts(prompts)
    except PromptIdConflictError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    # Deduplicate by ID (keep first occurrence)
    seen_ids: set[str] = set()
    unique_prompts = []
    for prompt in prompts:
        if prompt.id not in seen_ids:
            seen_ids.add(prompt.id)
            unique_prompts.append(prompt)
    
    # Create table for display
    table = Table(title="Discovered Prompts")
    table.add_column("ID", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Type", style="green")
    table.add_column("Status", style="yellow")
    
    created_count = 0
    skipped_count = 0
    
    # For single-file mode, load existing prompts
    existing_prompts: dict[str, dict] = {}
    if use_single_file and prompts_file.exists():
        try:
            existing_prompts = load_prompts_file(prompts_file)
        except Exception:
            existing_prompts = {}
    
    new_prompts: dict[str, dict] = {}
    
    for prompt in unique_prompts:
        prompt_type = "decorator" if prompt.is_decorator else "inline"
        rel_source = Path(prompt.source_file).name + f":{prompt.line_number}"
        
        if use_single_file:
            # Single-file mode
            if prompt.id in existing_prompts:
                status = "exists"
                skipped_count += 1
            else:
                status = "new"
                created_count += 1
                new_prompts[prompt.id] = {
                    "description": f"Auto-generated from {rel_source}",
                    "template": prompt.default_content,
                }
        else:
            # Multi-file mode
            yaml_path = prompts_dir / prompt.id / "v1.yaml"
            
            if yaml_path.exists():
                status = "exists"
                skipped_count += 1
            else:
                status = "new"
                created_count += 1
                
                if not dry_run:
                    save_yaml_template(
                        yaml_path,
                        template=prompt.default_content,
                        version="v1",
                        description=f"Auto-generated from {rel_source}",
                    )
        
        table.add_row(prompt.id, rel_source, prompt_type, status)
    
    console.print(table)
    
    # Save new prompts in single-file mode
    if use_single_file and new_prompts and not dry_run:
        # Merge existing and new prompts
        merged_prompts = {**existing_prompts, **new_prompts}
        save_prompts_file(prompts_file, merged_prompts)
    
    if dry_run:
        if use_single_file:
            console.print(f"\n[yellow]Dry run:[/yellow] Would add {created_count} prompts, skip {skipped_count}")
        else:
            console.print(f"\n[yellow]Dry run:[/yellow] Would create {created_count} files, skip {skipped_count}")
    else:
        if use_single_file:
            console.print(f"\n[green]Added:[/green] {created_count} prompts, [yellow]Skipped:[/yellow] {skipped_count}")
        else:
            console.print(f"\n[green]Created:[/green] {created_count} files, [yellow]Skipped:[/yellow] {skipped_count}")


@app.command()
def switch(
    prompt_id: str = typer.Argument(
        ...,
        help="Prompt ID to switch version",
    ),
    version: str = typer.Argument(
        ...,
        help="Version to switch to (e.g., v2)",
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project", "-p",
        help="Project root directory",
    ),
) -> None:
    """
    Switch a prompt to a specific version in the lockfile.
    """
    # Find project root
    if project_dir:
        project_root = project_dir.resolve()
    else:
        current = Path.cwd()
        project_root = None
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists():
                project_root = current
                break
            current = current.parent
        
        if project_root is None:
            console.print("[red]Error:[/red] No .prompt_lock.json found. Run 'pvcs init' first.")
            raise typer.Exit(1)
    
    lockfile_path = project_root / LOCKFILE_NAME
    yaml_path = project_root / PROMPTS_DIR / prompt_id / f"{version}.yaml"
    
    # Check if the version file exists
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] Version file not found: {yaml_path}")
        console.print(f"[dim]Available versions in prompts/{prompt_id}/:[/dim]")
        
        prompt_dir = project_root / PROMPTS_DIR / prompt_id
        if prompt_dir.exists():
            for f in prompt_dir.glob("*.yaml"):
                console.print(f"  - {f.stem}")
        else:
            console.print("  (none)")
        
        raise typer.Exit(1)
    
    # Load and update lockfile
    with open(lockfile_path, "r", encoding="utf-8") as f:
        lockfile = json.load(f)
    
    old_version = lockfile.get(prompt_id)
    lockfile[prompt_id] = version
    
    with open(lockfile_path, "w", encoding="utf-8") as f:
        json.dump(lockfile, f, indent=2, ensure_ascii=False)
    
    if old_version:
        console.print(f"[green]✓[/green] Switched '{prompt_id}': {old_version} → {version}")
    else:
        console.print(f"[green]✓[/green] Locked '{prompt_id}' to version {version}")


@app.command()
def status(
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project", "-p",
        help="Project root directory",
    ),
) -> None:
    """
    Show current lockfile status.
    """
    # Find project root
    if project_dir:
        project_root = project_dir.resolve()
    else:
        current = Path.cwd()
        project_root = None
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists():
                project_root = current
                break
            current = current.parent
        
        if project_root is None:
            console.print("[red]Error:[/red] No .prompt_lock.json found. Run 'pvcs init' first.")
            raise typer.Exit(1)
    
    lockfile_path = project_root / LOCKFILE_NAME
    
    with open(lockfile_path, "r", encoding="utf-8") as f:
        lockfile = json.load(f)
    
    if not lockfile:
        console.print("[yellow]Lockfile is empty.[/yellow] No prompts are version-locked.")
        return
    
    table = Table(title="Locked Prompts")
    table.add_column("Prompt ID", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("File Status", style="yellow")
    
    for prompt_id, version in sorted(lockfile.items()):
        yaml_path = project_root / PROMPTS_DIR / prompt_id / f"{version}.yaml"
        file_status = "✓" if yaml_path.exists() else "✗ missing"
        table.add_row(prompt_id, version, file_status)
    
    console.print(table)


@app.command()
def migrate(
    path: Path = typer.Argument(
        ...,
        help="File or directory to migrate",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run", "-n",
        help="Show changes without applying them",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Apply all changes without confirmation",
    ),
    clean: bool = typer.Option(
        False,
        "--clean", "-c",
        help="Extract prompt to YAML file and remove string from code",
    ),
) -> None:
    """
    Migrate hardcoded prompt strings to p() calls.
    
    Scans Python files for variables named 'prompt', 'template', 'instruction', or 'msg'
    and converts them to use the prompt-vcs library.
    
    Supports:
    - Simple strings
    - F-strings (with variable extraction)
    - Format spec preservation (e.g., :.2f)
    
    With --clean mode:
    - Extracts prompt content to prompts/{id}/v1.yaml
    - Generates p() calls without default content
    - Skips existing YAML files (won't overwrite)
    """
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.prompt import Confirm
    
    from prompt_vcs.codemod import migrate_file_content
    
    target_path = path.resolve()
    
    if not target_path.exists():
        console.print(f"[red]Error:[/red] Path not found: {target_path}")
        raise typer.Exit(1)
    
    # Find project root for clean mode
    project_root: Optional[Path] = None
    use_single_file = False  # Track which mode we're using
    if clean:
        current = target_path if target_path.is_dir() else target_path.parent
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists() or (current / ".git").exists():
                project_root = current
                break
            current = current.parent
        
        if project_root is None:
            project_root = Path.cwd()
            console.print(f"[yellow]Warning:[/yellow] No project root found, using current directory: {project_root}")
        else:
            console.print(f"[blue]Project root:[/blue] {project_root}")
        
        # Detect single-file vs multi-file mode
        prompts_yaml_path = project_root / PROMPTS_FILE
        if prompts_yaml_path.exists():
            use_single_file = True
            console.print(f"[blue]Clean mode:[/blue] Prompts will be written to {prompts_yaml_path.name}\n")
        else:
            console.print(f"[blue]Clean mode:[/blue] Prompts will be written to {project_root / PROMPTS_DIR}/\n")
    
    # Collect Python files
    if target_path.is_file():
        if not target_path.suffix == ".py":
            console.print(f"[red]Error:[/red] Not a Python file: {target_path}")
            raise typer.Exit(1)
        py_files = [target_path]
    else:
        py_files = list(target_path.rglob("*.py"))
    
    if not py_files:
        console.print("[yellow]No Python files found.[/yellow]")
        return
    
    console.print(f"[blue]Scanning:[/blue] {len(py_files)} Python file(s)\n")
    
    total_candidates = 0
    applied_count = 0
    skipped_count = 0
    yaml_written_count = 0

    
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not read {py_file}: {e}")
            continue
        
        # First pass: collect candidates without applying
        _, candidates = migrate_file_content(
            content, 
            py_file.name, 
            apply_changes=False,
            clean_mode=clean,
            project_root=project_root,
        )
        
        if not candidates:
            continue
        
        console.print(f"\n[bold cyan]File:[/bold cyan] {py_file.relative_to(target_path.parent if target_path.is_file() else target_path)}")
        console.print(f"[dim]Found {len(candidates)} migration candidate(s)[/dim]\n")
        
        for candidate in candidates:
            total_candidates += 1
            
            # Show diff
            console.print(f"[bold]Line {candidate.line_number}:[/bold] [cyan]{candidate.variable_name}[/cyan] → [green]{candidate.prompt_id}[/green]")
            
            # In clean mode, show YAML file status
            if clean and project_root:
                if use_single_file:
                    console.print("[green]  → Will add to:[/green] prompts.yaml")
                else:
                    yaml_path = project_root / PROMPTS_DIR / candidate.prompt_id / "v1.yaml"
                    if yaml_path.exists():
                        console.print(f"[yellow]  ⚠ YAML file exists, will skip:[/yellow] {yaml_path.relative_to(project_root)}")
                    else:
                        console.print(f"[green]  → Will create:[/green] {yaml_path.relative_to(project_root)}")
            
            # Original code (red)
            console.print(Panel(
                Syntax(candidate.original_code.strip(), "python", theme="monokai"),
                title="[red]Before[/red]",
                border_style="red",
            ))
            
            # New code (green)
            console.print(Panel(
                Syntax(candidate.new_code.strip(), "python", theme="monokai"),
                title="[green]After[/green]",
                border_style="green",
            ))
            
            if dry_run:
                console.print("[yellow]Dry run - no changes applied[/yellow]\n")
                skipped_count += 1
                continue
            
            # Ask for confirmation
            if yes or Confirm.ask("Apply this change?", default=True):
                applied_count += 1
            else:
                skipped_count += 1
                console.print("[dim]Skipped[/dim]\n")
        
        # If any changes were approved, apply them all at once
        if not dry_run and applied_count > 0:
            modified_content, applied_candidates = migrate_file_content(
                content, 
                py_file.name, 
                apply_changes=True,
                clean_mode=clean,
                project_root=project_root,
            )
            py_file.write_text(modified_content, encoding="utf-8")
            console.print(f"[green]✓[/green] Applied changes to {py_file.name}")
            
            # In clean mode, report YAML file status
            if clean and project_root:
                if use_single_file:
                    yaml_written_count += len(applied_candidates)
                    console.print(f"[green]  ✓[/green] Added {len(applied_candidates)} prompt(s) to prompts.yaml")
                else:
                    for cand in applied_candidates:
                        yaml_path = project_root / PROMPTS_DIR / cand.prompt_id / "v1.yaml"
                        if yaml_path.exists():
                            # Check if we just created it (file mtime is recent)
                            yaml_written_count += 1
                            console.print(f"[green]  ✓[/green] Created: {yaml_path.relative_to(project_root)}")
    
    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]Migration Summary[/bold]")
    console.print(f"  Total candidates: {total_candidates}")
    if not dry_run:
        console.print(f"  [green]Applied:[/green] {applied_count}")
        console.print(f"  [yellow]Skipped:[/yellow] {skipped_count}")
        if clean:
            console.print(f"  [green]YAML files created:[/green] {yaml_written_count}")
    else:
        console.print("  [yellow]Dry run - no changes applied[/yellow]")


@app.command()
def diff(
    prompt_id: str = typer.Argument(
        ...,
        help="Prompt ID to compare",
    ),
    version1: str = typer.Argument(
        ...,
        help="First version (e.g., v1)",
    ),
    version2: str = typer.Argument(
        ...,
        help="Second version (e.g., v2)",
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project", "-p",
        help="Project root directory",
    ),
) -> None:
    """
    Compare two versions of a prompt.
    
    Shows a unified diff between the two version files.
    """
    import difflib
    from rich.syntax import Syntax
    from rich.panel import Panel
    
    # Find project root
    if project_dir:
        project_root = project_dir.resolve()
    else:
        current = Path.cwd()
        project_root = None
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists() or (current / ".git").exists():
                project_root = current
                break
            current = current.parent
        
        if project_root is None:
            console.print("[red]Error:[/red] No project root found. Run 'pvcs init' first.")
            raise typer.Exit(1)
    
    # Check for single-file vs multi-file mode
    prompts_file = project_root / PROMPTS_FILE
    if prompts_file.exists():
        console.print("[yellow]Note:[/yellow] Single-file mode (prompts.yaml) does not support versioning.")
        console.print("[dim]Use multi-file mode with 'pvcs init --split' for version comparison.[/dim]")
        raise typer.Exit(1)
    
    # Build paths
    yaml_path1 = project_root / PROMPTS_DIR / prompt_id / f"{version1}.yaml"
    yaml_path2 = project_root / PROMPTS_DIR / prompt_id / f"{version2}.yaml"
    
    # Check files exist
    if not yaml_path1.exists():
        console.print(f"[red]Error:[/red] Version file not found: {yaml_path1}")
        raise typer.Exit(1)
    
    if not yaml_path2.exists():
        console.print(f"[red]Error:[/red] Version file not found: {yaml_path2}")
        raise typer.Exit(1)
    
    # Read contents
    content1 = yaml_path1.read_text(encoding="utf-8").splitlines(keepends=True)
    content2 = yaml_path2.read_text(encoding="utf-8").splitlines(keepends=True)
    
    # Generate diff
    diff_lines = list(difflib.unified_diff(
        content1,
        content2,
        fromfile=f"prompts/{prompt_id}/{version1}.yaml",
        tofile=f"prompts/{prompt_id}/{version2}.yaml",
    ))
    
    if not diff_lines:
        console.print(f"[green]No differences[/green] between {version1} and {version2}")
        return
    
    # Display diff with syntax highlighting
    console.print(f"\n[bold]Diff:[/bold] {prompt_id} ({version1} → {version2})\n")
    
    diff_text = "".join(diff_lines)
    console.print(Panel(
        Syntax(diff_text, "diff", theme="monokai"),
        border_style="blue",
    ))


@app.command()
def log(
    prompt_id: str = typer.Argument(
        ...,
        help="Prompt ID to show history for",
    ),
    count: int = typer.Option(
        10,
        "--count", "-n",
        help="Number of commits to show",
    ),
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project", "-p",
        help="Project root directory",
    ),
) -> None:
    """
    Show Git commit history for a prompt.
    
    Displays recent commits that modified the prompt files.
    """
    import subprocess
    
    # Find project root
    if project_dir:
        project_root = project_dir.resolve()
    else:
        current = Path.cwd()
        project_root = None
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists() or (current / ".git").exists():
                project_root = current
                break
            current = current.parent
        
        if project_root is None:
            console.print("[red]Error:[/red] No project root found.")
            raise typer.Exit(1)
    
    # Check for .git directory
    if not (project_root / ".git").exists():
        console.print("[red]Error:[/red] Not a Git repository.")
        raise typer.Exit(1)
    
    # Determine path to show history for
    prompts_file = project_root / PROMPTS_FILE
    if prompts_file.exists():
        # Single-file mode: show history for prompts.yaml
        target_path = prompts_file
        console.print("[blue]Mode:[/blue] Single-file (prompts.yaml)")
    else:
        # Multi-file mode: show history for the prompt directory
        target_path = project_root / PROMPTS_DIR / prompt_id
        if not target_path.exists():
            console.print(f"[red]Error:[/red] Prompt not found: {prompt_id}")
            raise typer.Exit(1)
        console.print(f"[blue]Mode:[/blue] Multi-file (prompts/{prompt_id}/)")
    
    console.print(f"[blue]History for:[/blue] {prompt_id}\n")
    
    # Run git log
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"-n{count}",
                "--oneline",
                "--follow",
                "--",
                str(target_path.relative_to(project_root)),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            console.print(f"[red]Error:[/red] Git command failed: {result.stderr}")
            raise typer.Exit(1)
        
        if not result.stdout.strip():
            console.print("[yellow]No commits found for this prompt.[/yellow]")
            return
        
        # Display commits
        for line in result.stdout.strip().split("\n"):
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commit_hash, message = parts
                console.print(f"[cyan]{commit_hash}[/cyan] {message}")
            else:
                console.print(line)
                
    except FileNotFoundError:
        console.print("[red]Error:[/red] Git is not installed or not in PATH.")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

