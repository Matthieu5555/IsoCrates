"""Static repository analysis: file manifest, module map, and import graph.

Pure functions operating on the filesystem — no OpenHands dependency,
no network calls. Fully testable with filesystem fixtures.
"""

import dataclasses
import logging
import os
from pathlib import Path

from prompts import ENTRY_POINT_PATTERNS, IMPORT_PATTERNS

logger = logging.getLogger("isocrates.agent")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ModuleInfo:
    """A logical module discovered by static analysis of the repository."""
    name: str                              # e.g. "backend/app"
    top_dir: str                           # e.g. "backend"
    files: list[tuple[str, int]]           # [(relative_path, bytes), ...]
    total_bytes: int = 0
    token_estimate: int = 0                # total_bytes // 4
    languages: dict[str, int] = dataclasses.field(default_factory=dict)
    entry_points: list[str] = dataclasses.field(default_factory=list)
    imports_from: set[str] = dataclasses.field(default_factory=set)
    imported_by: set[str] = dataclasses.field(default_factory=set)


@dataclasses.dataclass(frozen=True)
class RepoAnalysis:
    """Complete static analysis result for a repository."""
    file_manifest: list[tuple[str, int]]
    token_estimate: int
    file_count: int
    total_bytes: int
    size_label: str                        # "small" | "medium" | "large"
    top_dirs: dict[str, int]
    module_map: dict[str, ModuleInfo]
    module_count: int


# ---------------------------------------------------------------------------
# Filter sets
# ---------------------------------------------------------------------------

SKIP_DIRS: set[str] = {
    ".git", "node_modules", "vendor", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", ".tox", "egg-info",
}

SOURCE_EXTS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt",
    ".md", ".yaml", ".yml", ".json", ".toml", ".sh", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte",
}

SKIP_NAMES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock",
    "Cargo.lock", "poetry.lock",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_repository(repo_path: Path, crate: str = "") -> RepoAnalysis:
    """Walk *repo_path* and return a complete static analysis.

    This is the single entry point for all repo-analysis needs.
    The optional *crate* prefix is currently unused but reserved for
    future per-crate scoping.
    """
    file_manifest, total_bytes, top_dirs = _walk_files(repo_path)
    file_manifest.sort(key=lambda x: x[0])
    token_estimate = total_bytes // 4

    if token_estimate < 50_000:
        size_label = "small"
    elif token_estimate < 200_000:
        size_label = "medium"
    else:
        size_label = "large"

    module_map = _build_module_map(file_manifest, repo_path)

    return RepoAnalysis(
        file_manifest=file_manifest,
        token_estimate=token_estimate,
        file_count=len(file_manifest),
        total_bytes=total_bytes,
        size_label=size_label,
        top_dirs=dict(sorted(top_dirs.items(), key=lambda x: -x[1])),
        module_map=module_map,
        module_count=len(module_map),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _walk_files(
    repo_path: Path,
) -> tuple[list[tuple[str, int]], int, dict[str, int]]:
    """Walk the repo tree and collect source files.

    Returns (file_manifest, total_bytes, top_dirs).
    """
    file_manifest: list[tuple[str, int]] = []
    top_dirs: dict[str, int] = {}
    total_bytes = 0

    try:
        repo_str = str(repo_path)
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if fname in SKIP_NAMES:
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SOURCE_EXTS:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                except OSError:
                    continue
                if size > 512_000:  # skip >500KB (generated/minified)
                    continue
                rel = os.path.relpath(fpath, repo_str)
                file_manifest.append((rel, size))
                total_bytes += size
                top_dir = rel.split(os.sep)[0] if os.sep in rel else "."
                top_dirs[top_dir] = top_dirs.get(top_dir, 0) + size
    except OSError as e:
        logger.warning("Filesystem walk failed, using fallback estimates: %s", e)
        total_bytes = 80_000
        file_manifest = []
        top_dirs = {}

    return file_manifest, total_bytes, top_dirs


def _build_module_map(
    file_manifest: list[tuple[str, int]],
    repo_path: Path,
) -> dict[str, ModuleInfo]:
    """Group files into logical modules based on directory structure.

    Uses the first 2 path segments as module boundary (e.g. "backend/app").
    Modules with fewer than 3 files are merged into their parent.
    """
    # Group by first 2 path segments
    raw_groups: dict[str, list[tuple[str, int]]] = {}
    for fpath, fsize in file_manifest:
        parts = Path(fpath).parts
        if len(parts) >= 2:
            module_name = f"{parts[0]}/{parts[1]}"
        else:
            module_name = "."
        raw_groups.setdefault(module_name, []).append((fpath, fsize))

    # Merge small modules (< 3 files) into parent
    merged: dict[str, list[tuple[str, int]]] = {}
    for mod_name, files in raw_groups.items():
        if len(files) < 3 and mod_name != ".":
            parent = mod_name.split("/")[0]
            merged.setdefault(parent, []).extend(files)
        else:
            merged.setdefault(mod_name, []).extend(files)

    # Build ModuleInfo for each group
    modules: dict[str, ModuleInfo] = {}
    for mod_name, files in merged.items():
        total_bytes = sum(size for _, size in files)
        languages: dict[str, int] = {}
        entry_points: list[str] = []

        for fpath, _ in files:
            ext = Path(fpath).suffix
            if ext:
                languages[ext] = languages.get(ext, 0) + 1
            fname = Path(fpath).name
            if any(fname.startswith(p.rstrip(".")) or fname == p for p in ENTRY_POINT_PATTERNS):
                entry_points.append(fpath)

        top_dir = mod_name.split("/")[0] if "/" in mod_name else mod_name
        modules[mod_name] = ModuleInfo(
            name=mod_name,
            top_dir=top_dir,
            files=files,
            total_bytes=total_bytes,
            token_estimate=total_bytes // 4,
            languages=languages,
            entry_points=entry_points,
        )

    _build_import_graph(modules, repo_path)
    return modules


def _build_import_graph(
    modules: dict[str, ModuleInfo],
    repo_path: Path,
) -> None:
    """Populate imports_from/imported_by via regex-based import detection.

    Reads the first 100 lines of each source file to find import statements.
    Maps import paths to known module names via prefix matching.
    Modifies *modules* in-place.
    """
    path_to_module: dict[str, str] = {}
    for mod_name, mod_info in modules.items():
        for fpath, _ in mod_info.files:
            dir_path = str(Path(fpath).parent)
            path_to_module[dir_path] = mod_name
            parts = Path(fpath).parts
            if parts:
                path_to_module[parts[0]] = mod_name

    module_names = set(modules.keys())

    for mod_name, mod_info in modules.items():
        for fpath, _ in mod_info.files:
            ext = Path(fpath).suffix
            patterns = IMPORT_PATTERNS.get(ext, [])
            if not patterns:
                continue

            full_path = repo_path / fpath
            if not full_path.exists():
                continue

            try:
                with open(full_path, "r", errors="ignore") as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= 100:
                            break
                        lines.append(line)
            except (OSError, UnicodeDecodeError):
                continue

            for line in lines:
                for pattern in patterns:
                    match = pattern.search(line)
                    if not match:
                        continue
                    import_path = match.group(1)

                    import_as_path = import_path.replace(".", "/")
                    for target_mod in module_names:
                        if target_mod == mod_name:
                            continue
                        if (import_as_path.startswith(target_mod)
                                or import_path.startswith(target_mod)
                                or target_mod in import_as_path):
                            mod_info.imports_from.add(target_mod)
                            modules[target_mod].imported_by.add(mod_name)
                            break
