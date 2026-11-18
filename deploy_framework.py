#!/usr/bin/env python3
"""
Simulacra Framework Deployment & Scaffolding Script
-------------------------------------------------------------
Distributes the Cognitive Pipeline, book-writing layer, simulator, and craft
mechanics to other book folders in the same parent directory as this repo.

Launch (OS-aware):
  python scripts/run.py deploy [target]
  scripts/unix/deploy.sh              # Unix
  scripts/windows/deploy.ps1          # Windows

It can:
1. Initialize a brand-new book folder with the correct structure and framework files.
2. Update/sync the framework in an *allowlisted* book folder without touching custom files.
3. Present an interactive selection menu of allowlisted targets only.

IMPORTANT: This never scans the whole drive as deploy targets. Only names in
DEPLOY_ALLOWLIST (or an explicit CLI path) receive framework files. That prevents
accidental deploys into Keys/, Legal/, Provider/, etc.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

# Active downstream products only (receive framework deploys).
# Completed manuscripts stay OFF this list — do not bulk-update them:
#   BeliefAndLove, A Wanderers Guide To the Gates, history_of_the_great_wheel
# The framework repo itself (Simulacra) is never a deploy target — see is_blocked_target.
DEPLOY_ALLOWLIST = frozenset({
    "CharacterSimulator",
})

# Core: Cognitive Pipeline + Main + Rules + realm_data + state schema + templates.
#
# NOT deployed (author-local only; see LICENSE.md §3):
#   - Named character cards under Characters/
#   - Characters/Relations.md / filled logs
# Simulator/ is public — drop-in CharacterRuntime.
FRAMEWORK_FILES = [
    "Framework/Main.md",
    "Framework/CognitivePipeline.md",
    "Framework/Rules_Index.md",
    "Framework/Psychology/realm_data.yaml",
    "Framework/Schemas/psychosomatic_state.json",
    "Framework/natural_prose.md",
    "Framework/Drafting_Workflow.md",     # stub → Main
    "Framework/formatting_rules.md",
    "Framework/Design_QA_Protocol.md",
    "Framework/Drafting_Prompt.md",
    "Framework/Modules.md",
    "Framework/linter.py",
    "Framework/Continuity_Ledger.md",
    "Framework/Character_Change_Log.md",
    "Framework/source_changes.md",
    "Framework/degradation_protocol.md",
    "Framework/psyche_framework.md",
    "Characters/_template.yaml",
    "Characters/_log_template.yaml",
    "Characters/README.md",
    "PROJECT_SCOPE.md",
    # Product identity files (README/CHANGELOG/LICENSE/DISCLAIMER/.gitignore)
    # are only seeded for *new* empty book folders — never overwrite an existing
    # downstream project's branding (e.g. CharacterSimulator README).
]

# Seeded only when initializing a brand-new empty target directory.
NEW_BOOK_IDENTITY_FILES = [
    ".gitignore",
    "README.md",
    "CHANGELOG.md",
    "LICENSE.md",
    "DISCLAIMER.md",
]

FRAMEWORK_DIRS = [
    "Framework/Mechanics",
    "Framework/Psychology",
    "Framework/Schemas",
    "Framework/Prompts",
    "scripts",
]

NEW_BOOK_DIRS = [
    "Drafts",
    "Build",
    "Releases",
    "Research",
]

GITIGNORE_CONTENT = """# OS / editor
.DS_Store
Thumbs.db
*~
*.swp
.idea/
.vscode/
.venv-docx/

# Python
__pycache__/
*.pyc
"""

def get_source_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))

def get_parent_dir() -> str:
    return os.path.dirname(get_source_dir())

def is_blocked_target(target_dir: str) -> bool:
    """Hard-block deploys into the framework itself and known non-book trees."""
    name = os.path.basename(os.path.abspath(target_dir).rstrip(os.sep))
    blocked = {
        "Simulacra",  # this framework repo itself — never deploy into itself
        "Authors_Framework",
        "CharacterSimulator.UI",  # legacy folder name
        "Keys",
        "Legal",
        "Provider",
        "Backups",
        "tmp",
        "Code",
        ".obsidian",
        ".git",
    }
    return name in blocked


def get_book_directories(parent_dir: str) -> List[str]:
    """Return only allowlisted downstream project paths that currently exist."""
    if not os.path.exists(parent_dir):
        return []
    candidates: List[str] = []
    for name in sorted(DEPLOY_ALLOWLIST):
        path = os.path.join(parent_dir, name)
        if os.path.isdir(path):
            candidates.append(path)
    return candidates

def copy_file(src: str, dst: str) -> None:
    """Copy a file, creating target directory if missing."""
    dst_dir = os.path.dirname(dst)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"    Copied: {os.path.relpath(dst, get_parent_dir())}")

def copy_directory(src_dir: str, dst_dir: str) -> None:
    """Recursively copy directory contents (sync/overwrite)."""
    if not os.path.exists(src_dir):
        return
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir, exist_ok=True)
    
    for root, dirs, files in os.walk(src_dir):
        # Prune cache and private directories
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "Private", "private"}]
        rel_path = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel_path == '.' else os.path.join(dst_dir, rel_path)
        os.makedirs(target_root, exist_ok=True)
        
        for file in files:
            if file.endswith(('.pyc', '.pyo', '.tmp')) or file in {'.DS_Store', 'Thumbs.db'}:
                continue
            src_file = os.path.join(root, file)
            dst_file = os.path.join(target_root, file)
            shutil.copy2(src_file, dst_file)
    print(f"    Synced folder: {os.path.relpath(dst_dir, get_parent_dir())}")

def validate_source_files(source_dir: str) -> Tuple[List[str], List[str]]:
    """Validate that all framework files and directories exist.
    Returns tuple of (missing_files, missing_dirs)."""
    missing_files: List[str] = []
    missing_dirs: List[str] = []
    
    for rel_file in FRAMEWORK_FILES:
        src = os.path.join(source_dir, rel_file)
        if not os.path.exists(src):
            missing_files.append(rel_file)
    
    for rel_dir in FRAMEWORK_DIRS:
        src = os.path.join(source_dir, rel_dir)
        if not os.path.exists(src):
            missing_dirs.append(rel_dir)
    
    return missing_files, missing_dirs


def deploy_to_path(source_dir: str, target_dir: str, *, force: bool = False) -> None:
    """Deploys framework to the target path. Initializes if new folder.

    By default the target basename must be on DEPLOY_ALLOWLIST (or force=True
    for an explicit intentional deploy of a new name after confirmation).
    """
    parent_dir = get_parent_dir()
    target_name = os.path.basename(os.path.abspath(target_dir).rstrip(os.sep))

    if is_blocked_target(target_dir):
        print(f"\n[!] Refusing deploy into blocked path: {target_name}")
        print("    This is the framework repo itself or a non-book workspace.")
        return

    if not force and target_name not in DEPLOY_ALLOWLIST:
        print(f"\n[!] Refusing deploy into '{target_name}' — not on DEPLOY_ALLOWLIST.")
        print("    Add the folder name to DEPLOY_ALLOWLIST in deploy_framework.py")
        print("    if this is an intentional downstream book/app project.")
        return

    # Validate all source files exist before starting deployment
    missing_files, missing_dirs = validate_source_files(source_dir)
    if missing_files or missing_dirs:
        print(f"\n[!] Cannot deploy: missing source files or directories")
        for f in missing_files:
            print(f"    Missing file: {f}")
        for d in missing_dirs:
            print(f"    Missing directory: {d}")
        print("    Please ensure all framework files are present in the source directory.")
        return

    print(f"\n[+] Deploying framework to: {target_dir}")
    
    # Check if target is a new book directory (empty or doesn't exist)
    is_new = not os.path.exists(target_dir) or len(os.listdir(target_dir)) == 0
    
    # Create target directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)
    
    # If new book directory, set up the standard folders and gitignore
    if is_new:
        print("  -> Initializing new book folder structure...")
        for folder in NEW_BOOK_DIRS:
            os.makedirs(os.path.join(target_dir, folder), exist_ok=True)
            print(f"    Created directory: {folder}/")
            
        gitignore_path = os.path.join(target_dir, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as f:
                f.write(GITIGNORE_CONTENT)
            print("    Created: .gitignore")
            
    # Copy framework files
    print("  -> Deploying framework files...")
    for rel_file in FRAMEWORK_FILES:
        src = os.path.join(source_dir, rel_file)
        dst = os.path.join(target_dir, rel_file)
        if os.path.exists(src):
            copy_file(src, dst)
        else:
            print(f"    [WARNING] Source file not found: {rel_file}")

    # Identity files: only when creating a new book, or if the target file is missing
    if is_new:
        print("  -> Seeding new-book identity files...")
        for rel_file in NEW_BOOK_IDENTITY_FILES:
            src = os.path.join(source_dir, rel_file)
            dst = os.path.join(target_dir, rel_file)
            if os.path.exists(src):
                copy_file(src, dst)
    else:
        for rel_file in NEW_BOOK_IDENTITY_FILES:
            src = os.path.join(source_dir, rel_file)
            dst = os.path.join(target_dir, rel_file)
            if os.path.exists(src) and not os.path.exists(dst):
                copy_file(src, dst)
                print(f"    (seeded missing identity file: {rel_file})")

    # Copy framework directories
    for rel_dir in FRAMEWORK_DIRS:
        src = os.path.join(source_dir, rel_dir)
        dst = os.path.join(target_dir, rel_dir)
        if os.path.exists(src):
            copy_directory(src, dst)
        else:
            print(f"    [WARNING] Source directory not found: {rel_dir}")

    # Remove core-retired files and directories that must not linger in downstream trees
    retired = [
        "Framework/Mechanics/erotica.md",
        "Framework/Psychology/realm_index.md",
        "migrate_optimized.py",
        "scripts/unix/migrate.sh",
        "scripts/windows/migrate.ps1",
        "scripts/windows/migrate.cmd",
    ]
    for rel in retired:
        stale = os.path.join(target_dir, rel)
        if os.path.isfile(stale):
            os.remove(stale)
            print(f"    Removed retired file: {rel}")

    retired_dirs = [
        "Simulator",
    ]
    for rel_d in retired_dirs:
        # Simulator was decoupled to CharacterSimulator; do not delete it there
        if target_name == "CharacterSimulator" and rel_d == "Simulator":
            continue
        stale_d = os.path.join(target_dir, rel_d)
        if os.path.isdir(stale_d):
            shutil.rmtree(stale_d)
            print(f"    Removed retired directory: {rel_d}/")

    print(f"[✓] Deployment to '{os.path.basename(target_dir)}' completed successfully!")
    print("  (Skipped author-local only: named character cards, Relations.md)")
    print("  (Skipped overwriting existing product README/CHANGELOG/LICENSE/DISCLAIMER)")

def main():
    source_dir = get_source_dir()
    parent_dir = get_parent_dir()
    
    print("==================================================")
    print("      Simulacra Framework Deployer      ")
    print("==================================================")
    
    # CLI: deploy [name-or-path] [--force]
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]

    if args:
        target = args[0]
        if not os.path.isabs(target):
            if os.path.sep in target:
                target = os.path.abspath(target)
            else:
                target = os.path.join(parent_dir, target)
        deploy_to_path(source_dir, target, force=force)
        return

    # Interactive Mode — allowlisted targets only
    books = get_book_directories(parent_dir)

    print("\nDeploy targets are allowlisted (not every folder on this drive).")
    print(f"Allowlist: {', '.join(sorted(DEPLOY_ALLOWLIST))}")
    print("\nAvailable options:")
    print("  [0] Create a new book folder (must confirm; add to allowlist for later bulk updates)")

    for i, book_path in enumerate(books, start=1):
        name = os.path.basename(book_path)
        print(f"  [{i}] Update existing book: {name}")

    if books:
        print(f"  [A] Update ALL allowlisted books ({len(books)} found)")

    print("  [Q] Quit")

    try:
        choice = input("\nSelect an option: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return

    if choice == "q":
        print("Exiting.")
        return
    elif choice == "0":
        new_name = input("Enter the name of the new book folder: ").strip()
        if not new_name:
            print("Invalid name. Exiting.")
            return
        if is_blocked_target(os.path.join(parent_dir, new_name)):
            print(f"[!] Name '{new_name}' is blocked.")
            return
        confirm = input(
            f"Create/deploy into '{new_name}'? "
            f"Remember to add it to DEPLOY_ALLOWLIST for future bulk updates. (y/n): "
        ).strip().lower()
        if confirm != "y":
            print("Operation cancelled.")
            return
        target = os.path.join(parent_dir, new_name)
        deploy_to_path(source_dir, target, force=True)
    elif choice == "a" and books:
        confirm = input(
            f"Update ALL {len(books)} allowlisted books? (y/n): "
        ).strip().lower()
        if confirm == "y":
            for book_path in books:
                deploy_to_path(source_dir, book_path)
        else:
            print("Operation cancelled.")
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(books):
                deploy_to_path(source_dir, books[idx])
            else:
                print("Invalid choice. Exiting.")
        except ValueError:
            print("Invalid input. Exiting.")

if __name__ == "__main__":
    main()
