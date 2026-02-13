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
    crates: list[dict] = dataclasses.field(default_factory=list)


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

# Package manifest files that indicate a module or sub-project boundary.
# Used by _detect_module_boundaries() for intelligent module grouping and
# by detect_crates() for automatic sub-project discovery.
MODULE_MARKERS: set[str] = {
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.py",
    "pom.xml", "build.gradle", "Gemfile", "composer.json",
    "CMakeLists.txt", "Package.swift",
}

# Subset of MODULE_MARKERS used for crate (independent sub-project) detection.
# Excludes language-internal markers (__init__.py, mod.rs) that indicate
# modules within a project rather than independent projects.
CRATE_MARKERS: set[str] = {
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.py",
    "pom.xml", "build.gradle", "Gemfile", "composer.json",
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
    crates = detect_crates(repo_path)

    return RepoAnalysis(
        file_manifest=file_manifest,
        token_estimate=token_estimate,
        file_count=len(file_manifest),
        total_bytes=total_bytes,
        size_label=size_label,
        top_dirs=dict(sorted(top_dirs.items(), key=lambda x: -x[1])),
        module_map=module_map,
        module_count=len(module_map),
        crates=crates,
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
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in SOURCE_EXTS:
                    continue
                try:
                    size = fpath.stat().st_size
                except OSError:
                    continue
                if size > 512_000:  # skip >500KB (generated/minified)
                    continue
                rel = fpath.relative_to(repo_path).as_posix()
                file_manifest.append((rel, size))
                total_bytes += size
                top_dir = Path(rel).parts[0] if Path(rel).parts[0] != rel else "."
                top_dirs[top_dir] = top_dirs.get(top_dir, 0) + size
    except OSError as e:
        logger.warning("Filesystem walk failed, using fallback estimates: %s", e)
        total_bytes = 80_000
        file_manifest = []
        top_dirs = {}

    return file_manifest, total_bytes, top_dirs


def _detect_module_boundaries(
    file_manifest: list[tuple[str, int]],
    repo_path: Path,
) -> dict[str, str]:
    """Map each file to its module based on nearest ancestor with a marker.

    For each file, walks up the directory tree looking for a MODULE_MARKERS
    file. The directory containing the nearest marker becomes the module
    boundary. Falls back to the first-2-path-segments heuristic when no
    marker is found within 4 ancestor levels.

    Returns {relative_file_path: module_name}.
    """
    # Cache: directory path → module name (or None if no marker found)
    _dir_cache: dict[str, str | None] = {}

    def _find_module_for_dir(rel_dir: str) -> str | None:
        """Walk up from *rel_dir* looking for a marker file."""
        if rel_dir in _dir_cache:
            return _dir_cache[rel_dir]

        parts = Path(rel_dir).parts if rel_dir != "." else ()
        # Check up to 4 ancestor levels (including the dir itself)
        for depth in range(len(parts), max(len(parts) - 4, -1), -1):
            ancestor = str(Path(*parts[:depth])) if depth > 0 else "."
            if ancestor in _dir_cache:
                result = _dir_cache[ancestor]
                # Cache the original path too
                _dir_cache[rel_dir] = result
                return result

            abs_ancestor = repo_path / ancestor if ancestor != "." else repo_path
            for marker in MODULE_MARKERS:
                if (abs_ancestor / marker).exists():
                    mod_name = ancestor if ancestor != "." else "."
                    _dir_cache[ancestor] = mod_name
                    _dir_cache[rel_dir] = mod_name
                    return mod_name

        _dir_cache[rel_dir] = None
        return None

    result: dict[str, str] = {}
    for fpath, _ in file_manifest:
        rel_dir = str(Path(fpath).parent) if str(Path(fpath).parent) != "." else "."
        module = _find_module_for_dir(rel_dir)
        if module is not None:
            result[fpath] = module
        else:
            # Fallback: first 2 path segments
            parts = Path(fpath).parts
            if len(parts) >= 2:
                result[fpath] = f"{parts[0]}/{parts[1]}"
            else:
                result[fpath] = "."
    return result


def _build_module_map(
    file_manifest: list[tuple[str, int]],
    repo_path: Path,
) -> dict[str, ModuleInfo]:
    """Group files into logical modules using marker-based boundary detection.

    First tries to detect module boundaries from package manifest files
    (package.json, Cargo.toml, etc.). Falls back to first-2-path-segments
    heuristic for files without nearby markers. Modules with fewer than
    3 files are merged into their parent.
    """
    boundaries = _detect_module_boundaries(file_manifest, repo_path)

    raw_groups: dict[str, list[tuple[str, int]]] = {}
    for fpath, fsize in file_manifest:
        module_name = boundaries.get(fpath, ".")
        raw_groups.setdefault(module_name, []).append((fpath, fsize))

    # Merge small modules (< 3 files) into parent
    merged: dict[str, list[tuple[str, int]]] = {}
    for mod_name, files in raw_groups.items():
        if len(files) < 3 and mod_name != ".":
            parent = mod_name.split("/")[0] if "/" in mod_name else "."
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


def detect_crates(repo_path: Path) -> list[dict]:
    """Detect independent sub-projects (crates) within a repository.

    Walks the repo looking for CRATE_MARKERS (package.json, Cargo.toml,
    go.mod, etc.) in subdirectories. The root project marker is excluded
    since it represents the repo itself, not a sub-project.

    Deduplication: if both ``backend/package.json`` and
    ``backend/api/package.json`` exist, keeps only the shallower one
    (the deeper one is considered an internal module, not a separate crate).

    Returns a list of dicts: ``[{"path": "packages/api", "marker": "package.json", "name": "api"}]``.
    """
    crates: list[dict] = []
    crate_paths: set[str] = set()

    try:
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            rel_root = Path(root).relative_to(repo_path).as_posix()
            if rel_root == ".":
                continue  # skip root — it's the repo itself, not a crate

            for fname in files:
                if fname in CRATE_MARKERS:
                    crate_paths.add(rel_root)
                    break  # one marker per directory is enough

    except OSError as e:
        logger.warning("Crate detection walk failed: %s", e)
        return []

    if not crate_paths:
        return []

    # Dedup: remove crates whose ancestor is also a crate.
    # Sort by depth (shallowest first) so ancestors are processed first.
    sorted_paths = sorted(crate_paths, key=lambda p: p.count("/"))
    kept: list[str] = []
    for cp in sorted_paths:
        if any(cp.startswith(ancestor + "/") for ancestor in kept):
            continue  # deeper path is a sub-module of an already-kept crate
        kept.append(cp)

    for cp in kept:
        # Find which marker was in this directory
        marker = ""
        for m in CRATE_MARKERS:
            if (repo_path / cp / m).exists():
                marker = m
                break
        name = Path(cp).name
        crates.append({"path": cp, "marker": marker, "name": name})

    return crates
