#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import argparse
import os

def run(cmd, cwd=None, dry_run=False):
    """Run a shell command, respect dry-run mode."""
    if dry_run:
        print(f"[DRY-RUN] {cmd} (cwd={cwd})")
        return 0
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode

def detect_project_dir():
    """Detect project directory using OLIPI_DIR env or script folder."""
    olipi_dir = os.environ.get("OLIPI_DIR")
    if olipi_dir:
        path = Path(olipi_dir).resolve()
        if path.exists():
            return path
    return Path(__file__).resolve().parent

def detect_venv_dir(project_dir):
    """Detect venv path from env or .venv folder in project."""
    venv_dir = os.environ.get("OLIPI_VENV")
    if venv_dir:
        path = Path(venv_dir).resolve()
        if path.exists():
            return path
    # fallback: .venv inside project dir
    fallback = project_dir / ".venv"
    if fallback.exists():
        return fallback
    # fallback: default in home
    return Path.home() / ".olipi-moode-venv"

def update_olipi(branch="main", dry_run=False):
    repo_dir = detect_project_dir()
    if not repo_dir.exists():
        print(f"Error: project directory {repo_dir} does not exist.")
        return

    # Check git repository
    if not (repo_dir / ".git").exists():
        print(f"Error: {repo_dir} is not a git repository.")
        return

    print(f"Project directory detected: {repo_dir}")
    print(f"Branch to update: {branch}")
    print(f"Dry-run mode: {'ON' if dry_run else 'OFF'}")

    # Detect local changes
    status = subprocess.run("git status --porcelain", shell=True, cwd=repo_dir,
                            capture_output=True, text=True)
    local_changes = status.stdout.strip()
    if local_changes:
        print("WARNING: local changes detected, update may fail or require conflict resolution:")
        print(local_changes)

    # Prompt user
    prompt_msg = "Proceed with updating OliPi-Moode and its submodule from Git? [y/N] "
    if dry_run:
        print(f"[DRY-RUN] Would prompt: {prompt_msg}")
    else:
        confirm = input(prompt_msg).strip().lower()
        if confirm not in ("y", "yes"):
            print("Update aborted by user.")
            return

    # Update main repo
    run("git fetch --all", cwd=repo_dir, dry_run=dry_run)
    run(f"git checkout {branch}", cwd=repo_dir, dry_run=dry_run)
    run(f"git pull origin {branch}", cwd=repo_dir, dry_run=dry_run)

    # Update submodules
    submodule_dir = repo_dir / "olipi_core"
    if submodule_dir.exists() and (submodule_dir / ".git").exists():
        print(f"Updating submodule olipi_core in {submodule_dir}")
        run("git submodule update --init --remote", cwd=repo_dir, dry_run=dry_run)
    else:
        print("No submodule olipi_core found or not initialized, skipping.")

    # Detect venv
    venv_dir = detect_venv_dir(repo_dir)
    python_bin = venv_dir / "bin/python3"
    pip_bin = venv_dir / "bin/pip"

    # Install dependencies
    req_file = repo_dir / "requirements.txt"
    if req_file.exists():
        if not venv_dir.exists():
            print(f"Virtualenv not found at {venv_dir}, creating...")
            run(f"python3 -m venv {venv_dir}", dry_run=dry_run)
        print("Installing/updating dependencies...")
        run(f"{pip_bin} install --upgrade -r {req_file}", dry_run=dry_run)

    print("Update completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update OliPi-Moode project via Git (user-safe)")
    parser.add_argument("--branch", default="main", help="Git branch to update (default: main)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the update without executing")
    args = parser.parse_args()

    update_olipi(branch=args.branch, dry_run=args.dry_run)
