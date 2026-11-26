"""Launch with an explicit separate development workspace outside the checkout."""
import argparse
import os
import stat
import sys
from pathlib import Path

MARKER = ".biddesk-emergent-development"
MAGIC = b"BidDesk Emergent source snapshot development workspace v1\n"
ROOT = Path(__file__).resolve().parent

def checked(path, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
        raise ValueError("A workspace cannot be a symbolic link, junction or redirected path.")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise ValueError("Unexpected file type in workspace.")

def select_workspace(argument, repo=ROOT):
    selected = Path(argument).expanduser().absolute()
    if os.path.lexists(selected):
        checked(selected, True)
    selected = selected.resolve()
    repo = Path(repo).resolve()
    if selected == repo or selected.is_relative_to(repo) or repo.is_relative_to(selected):
        raise ValueError("Choose a separate folder outside the source checkout, not its parent.")
    if not selected.exists():
        selected.mkdir()  # only new leaf, never create a chain of unspecified directories
    marker = selected / MARKER
    if os.path.lexists(marker):
        checked(marker)
        if marker.read_bytes() != MAGIC:
            raise ValueError("A different application created this marker.")
    elif not any(selected.iterdir()):
        with marker.open("xb") as stream:
            stream.write(MAGIC)
    else:
        raise ValueError("Refusing to open an existing nonempty folder from another app or workspace.")
    for name in ("originals", "backups", "generated", "working", "biddesk.db", "biddesk.db-wal", "biddesk.db-shm", "biddesk.db-journal"):
        child = selected / name
        if os.path.lexists(child):
            checked(child, name in ("originals", "backups", "generated", "working"))
    return selected

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="new or existing dedicated development folder")
    args = parser.parse_args()
    try:
        from biddesk.ui import main as run_app
        workspace = select_workspace(args.workspace)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f"STOP: {error}\n")
    sys.argv[:] = [sys.argv[0], str(workspace)]
    return run_app()

if __name__ == "__main__":
    raise SystemExit(main())
