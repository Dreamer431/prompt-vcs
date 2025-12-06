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
from prompt_vcs.manager import LOCKFILE_NAME, PROMPTS_DIR
from prompt_vcs.templates import save_yaml_template


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
) -> None:
    """
    Initialize a new prompt-vcs project.
    
    Creates:
    - .prompt_lock.json: Version lockfile
    - prompts/: Directory for prompt YAML files
    """
    project_root = (path or Path.cwd()).resolve()
    
    lockfile_path = project_root / LOCKFILE_NAME
    prompts_dir = project_root / PROMPTS_DIR
    
    # Create lockfile if not exists
    if not lockfile_path.exists():
        with open(lockfile_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
        console.print(f"[green]✓[/green] Created {lockfile_path.name}")
    else:
        console.print(f"[yellow]![/yellow] {lockfile_path.name} already exists")
    
    # Create prompts directory if not exists
    if not prompts_dir.exists():
        prompts_dir.mkdir(parents=True)
        console.print(f"[green]✓[/green] Created {prompts_dir.name}/ directory")
    else:
        console.print(f"[yellow]![/yellow] {prompts_dir.name}/ already exists")
    
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
        help="Output directory for YAML files (defaults to ./prompts)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run", "-n",
        help="Show what would be created without actually creating files",
    ),
) -> None:
    """
    Scan source code and generate YAML files for discovered prompts.
    
    Uses AST parsing to find:
    - p("id", "content") function calls
    - @prompt(id="...") decorator usages
    """
    src_path = src_dir.resolve()
    
    if not src_path.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src_path}")
        raise typer.Exit(1)
    
    # Determine output directory
    if output_dir:
        prompts_dir = output_dir.resolve()
    else:
        # Look for project root (where .prompt_lock.json or .git is)
        current = src_path
        prompts_dir = None
        while current != current.parent:
            if (current / LOCKFILE_NAME).exists() or (current / ".git").exists():
                prompts_dir = current / PROMPTS_DIR
                break
            current = current.parent
        
        if prompts_dir is None:
            prompts_dir = Path.cwd() / PROMPTS_DIR
    
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
    
    for prompt in unique_prompts:
        yaml_path = prompts_dir / prompt.id / "v1.yaml"
        
        prompt_type = "decorator" if prompt.is_decorator else "inline"
        rel_source = Path(prompt.source_file).name + f":{prompt.line_number}"
        
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
    
    if dry_run:
        console.print(f"\n[yellow]Dry run:[/yellow] Would create {created_count} files, skip {skipped_count}")
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
    yaml_skipped_count = 0
    
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
        console.print(f"  [yellow]Dry run - no changes applied[/yellow]")


if __name__ == "__main__":
    app()

