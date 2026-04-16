from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

from .schema import SUPPORTED_LANGUAGES, FileRecord, RepoIndex
from .utils import repo_node_id, sha256_bytes

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".venv", "venv"}


def _git_root(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _iter_git_tracked_and_untracked(repo_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    return [repo_root / line.strip() for line in result.stdout.splitlines() if line.strip()]


def _iter_fallback(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _infer_language(path: Path) -> str | None:
    return SUPPORTED_LANGUAGES.get(path.suffix.lower())


def _git_ref(repo_root: Path, ref: str | None = None) -> str | None:
    command = ["git", "rev-parse", ref or "HEAD"]
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def index_repository(
    repo_root: Path,
    *,
    target_languages: set[str] | None = None,
    only_paths: set[str] | None = None,
    git_ref: str | None = None,
    repo_identity: str | Path | None = None,
) -> RepoIndex:
    repo_root = repo_root.resolve()
    candidates = _iter_git_tracked_and_untracked(repo_root) if _git_root(repo_root) else []
    if not candidates:
        candidates = list(_iter_fallback(repo_root))

    files: list[FileRecord] = []
    directories: set[str] = set()
    packages: set[str] = set()
    allowed = target_languages or set(SUPPORTED_LANGUAGES.values())
    only = {p.replace("\\", "/") for p in (only_paths or set())}

    for path in sorted(candidates):
        language = _infer_language(path)
        if language is None or language not in allowed:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        if only and rel_path not in only:
            continue
        data = path.read_bytes()
        files.append(
            FileRecord(
                path=path,
                repo_root=repo_root,
                language=language,
                sha256=sha256_bytes(data),
                size=path.stat().st_size,
                last_modified=path.stat().st_mtime,
                git_ref=git_ref,
            ),
        )
        parent = Path(rel_path).parent
        while parent and parent.as_posix() != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
        if path.name == "__init__.py" and path.parent != repo_root:
            packages.add(path.parent.relative_to(repo_root).as_posix())
        if path.name in {"package.json", "pom.xml"} and path.parent != repo_root:
            packages.add(path.parent.relative_to(repo_root).as_posix())

    return RepoIndex(
        repo_root=repo_root,
        repo_id=repo_node_id(
            Path(repo_identity).resolve() if repo_identity is not None else repo_root
        ),
        files=files,
        directories=sorted(directories),
        packages=sorted(packages),
        git_ref=_git_ref(repo_root, git_ref),
    )
