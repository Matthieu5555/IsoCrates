"""Partition a repository's module graph into documentation areas.

When a codebase is too large for a single planner pass, this module
splits it into coherent areas using community detection on the import
graph. Each area becomes an independent scout → planner → writer
pipeline, with a final integration pass for cross-cutting hub pages.

The single entry point is ``partition_for_documentation``. It returns
a one-element list when splitting is not warranted, so callers never
need to branch on "was it partitioned?".

Algorithm: Label Propagation (weighted by token estimate) on the
undirected import graph, with directory-based fallback when the graph
has no edges or converges to a single community. Merge/split passes
enforce a 3–7 area target.  Zero external dependencies.
"""

from __future__ import annotations

import dataclasses
import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_analysis import ModuleInfo, RepoAnalysis

logger = logging.getLogger("isocrates.agent.partitioner")

# ---------------------------------------------------------------------------
# Partitioning thresholds
# ---------------------------------------------------------------------------

# Repo must exceed this multiple of the planner's context window to trigger
# splitting.  At 2×, scout reports would need ~50% compression in the
# single-area path — splitting gives each area full-fidelity reports instead.
_BUDGET_MULTIPLIER = 2

# Minimum number of detected modules before partitioning is considered.
# Below 4, the planner can reason about the whole module map in one pass.
_MIN_MODULE_COUNT = 4

# Allowed range for the number of documentation areas.
_MIN_AREAS = 3
_MAX_AREAS = 7

# Label Propagation: deterministic seed and iteration cap.
_LPA_SEED = 42
_LPA_MAX_ITERATIONS = 50


# ---------------------------------------------------------------------------
# Public data structure
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DocumentationArea:
    """A partition of the repository scoped to fit a planner's context window.

    Each area is an independent unit for the scout → planner → writer
    pipeline. ``is_integration`` is always ``False`` here — the concept
    of integration docs lives in the orchestrator, not the partitioner.

    Attributes:
        name:           Human-readable label, e.g. "API Layer".
        module_names:   Modules belonging to this area (tuple for frozen).
        files:          All source files from these modules, ``(rel_path, bytes)``.
        token_estimate: Sum of module token estimates.
        is_integration: Always False.  Present for type completeness.
    """

    name: str
    module_names: tuple[str, ...]
    files: tuple[tuple[str, int], ...]
    token_estimate: int
    is_integration: bool = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def partition_for_documentation(
    analysis: RepoAnalysis,
    context_budget: int,
    *,
    min_areas: int = _MIN_AREAS,
    max_areas: int = _MAX_AREAS,
) -> list[DocumentationArea]:
    """Decide whether and how to split a repository into documentation areas.

    Returns a **single-element list** when splitting is not warranted
    (small repo, few modules, or fits in context).  The caller always
    iterates over the result without needing to check length.

    Args:
        analysis:       Complete ``RepoAnalysis`` from ``analyze_repository()``.
        context_budget: Planner's context window in tokens.
        min_areas:      Floor for area count (default 3).
        max_areas:      Ceiling for area count (default 7).
    """
    module_map = analysis.module_map

    # Guard: skip when partitioning would not help
    if (
        analysis.token_estimate < _BUDGET_MULTIPLIER * context_budget
        or analysis.module_count < _MIN_MODULE_COUNT
    ):
        return [_single_area(analysis)]

    logger.info(
        "Partitioning: %s tokens, %d modules, context_budget=%d",
        f"{analysis.token_estimate:,}",
        analysis.module_count,
        context_budget,
    )

    adj = _build_adjacency(module_map)

    if _has_edges(adj):
        labels = _label_propagation(adj, module_map)
        groups = _labels_to_groups(labels)
        # If LPA collapsed everything into one community, the graph is
        # too densely connected for topological splitting — fall back to
        # directory structure.
        if len(groups) < 2:
            labels = _group_by_directory(module_map)
            groups = _labels_to_groups(labels)
    else:
        labels = _group_by_directory(module_map)
        groups = _labels_to_groups(labels)

    # Still one group after directory fallback → force-split by size
    if len(groups) < 2:
        groups = _force_split_by_size(module_map, max_areas)

    # Balance: merge tiny areas, split huge ones, enforce bounds
    min_area_tokens = context_budget // max_areas
    max_area_tokens = context_budget * 2
    groups = _merge_small_groups(groups, adj, module_map, min_area_tokens)
    groups = _split_large_groups(groups, module_map, max_area_tokens, max_areas)
    groups = _enforce_bounds(groups, adj, module_map, min_areas, max_areas)

    areas = _assemble_areas(groups, module_map)
    logger.info("Partitioned into %d areas: %s", len(areas), [a.name for a in areas])
    return areas


# ---------------------------------------------------------------------------
# Adjacency graph
# ---------------------------------------------------------------------------

def _build_adjacency(module_map: dict[str, ModuleInfo]) -> dict[str, set[str]]:
    """Undirected adjacency from ``imports_from`` / ``imported_by``."""
    adj: dict[str, set[str]] = {name: set() for name in module_map}
    for name, info in module_map.items():
        for target in info.imports_from | info.imported_by:
            if target in adj:
                adj[name].add(target)
                adj[target].add(name)
    return adj


def _has_edges(adj: dict[str, set[str]]) -> bool:
    return any(neighbors for neighbors in adj.values())


# ---------------------------------------------------------------------------
# Label Propagation
# ---------------------------------------------------------------------------

def _label_propagation(
    adj: dict[str, set[str]],
    module_map: dict[str, ModuleInfo],
) -> dict[str, int]:
    """Weighted Label Propagation for community detection.

    Each node starts with a unique label.  On each iteration every node
    adopts the label that has the highest *weight* among its neighbors,
    where weight = sum of ``token_estimate`` for neighbors with that label.
    Ties are broken by smallest label for determinism.

    Returns ``{module_name: community_label}``.
    """
    rng = random.Random(_LPA_SEED)
    sorted_names = sorted(module_map)
    labels = {name: idx for idx, name in enumerate(sorted_names)}
    nodes = list(sorted_names)

    for _ in range(_LPA_MAX_ITERATIONS):
        rng.shuffle(nodes)
        changed = False
        for node in nodes:
            neighbors = adj.get(node, set())
            if not neighbors:
                continue
            votes: dict[int, int] = {}
            for nb in neighbors:
                lbl = labels[nb]
                weight = module_map[nb].token_estimate or 1
                votes[lbl] = votes.get(lbl, 0) + weight
            # Highest weight, break ties by smallest label (deterministic)
            best = max(votes, key=lambda l: (votes[l], -l))
            if labels[node] != best:
                labels[node] = best
                changed = True
        if not changed:
            break

    return labels


# ---------------------------------------------------------------------------
# Directory-based fallback
# ---------------------------------------------------------------------------

def _group_by_directory(module_map: dict[str, ModuleInfo]) -> dict[str, int]:
    """Group modules by their ``top_dir`` when import edges are absent."""
    dir_to_label: dict[str, int] = {}
    labels: dict[str, int] = {}
    next_label = 0
    for name in sorted(module_map):
        top = module_map[name].top_dir
        if top not in dir_to_label:
            dir_to_label[top] = next_label
            next_label += 1
        labels[name] = dir_to_label[top]
    return labels


# ---------------------------------------------------------------------------
# Force-split (last resort when everything lands in one group)
# ---------------------------------------------------------------------------

def _force_split_by_size(
    module_map: dict[str, ModuleInfo],
    target_groups: int,
) -> dict[int, list[str]]:
    """Round-robin assignment sorted by size descending."""
    sorted_names = sorted(module_map, key=lambda n: -module_map[n].token_estimate)
    k = min(target_groups, len(sorted_names))
    buckets: list[list[str]] = [[] for _ in range(k)]
    sizes = [0] * k
    for name in sorted_names:
        smallest = min(range(k), key=lambda i: sizes[i])
        buckets[smallest].append(name)
        sizes[smallest] += module_map[name].token_estimate
    return {i: b for i, b in enumerate(buckets) if b}


# ---------------------------------------------------------------------------
# Label → group conversion
# ---------------------------------------------------------------------------

def _labels_to_groups(labels: dict[str, int]) -> dict[int, list[str]]:
    groups: dict[int, list[str]] = {}
    for name, lbl in labels.items():
        groups.setdefault(lbl, []).append(name)
    return groups


# ---------------------------------------------------------------------------
# Merge / split / enforce
# ---------------------------------------------------------------------------

def _find_group(module_name: str, groups: dict[int, list[str]]) -> int | None:
    for gid, members in groups.items():
        if module_name in members:
            return gid
    return None


def _group_tokens(modules: list[str], module_map: dict[str, ModuleInfo]) -> int:
    return sum(module_map[m].token_estimate for m in modules)


def _merge_small_groups(
    groups: dict[int, list[str]],
    adj: dict[str, set[str]],
    module_map: dict[str, ModuleInfo],
    min_tokens: int,
) -> dict[int, list[str]]:
    """Iteratively merge the smallest under-threshold group into its most-connected neighbor."""
    merged = True
    while merged:
        merged = False
        for gid in sorted(groups, key=lambda g: _group_tokens(groups[g], module_map)):
            if _group_tokens(groups[gid], module_map) >= min_tokens:
                continue
            if len(groups) <= 2:
                break
            # Cross-edge counts to each neighbor group
            edge_counts: dict[int, int] = {}
            for mod in groups[gid]:
                for nb in adj.get(mod, set()):
                    nb_gid = _find_group(nb, groups)
                    if nb_gid is not None and nb_gid != gid:
                        edge_counts[nb_gid] = edge_counts.get(nb_gid, 0) + 1
            if edge_counts:
                target = max(edge_counts, key=edge_counts.get)  # type: ignore[arg-type]
            else:
                # No connected neighbor — merge into smallest other group
                target = min(
                    (g for g in groups if g != gid),
                    key=lambda g: _group_tokens(groups[g], module_map),
                )
            groups[target].extend(groups.pop(gid))
            merged = True
            break  # restart after mutation
    return groups


def _split_large_groups(
    groups: dict[int, list[str]],
    module_map: dict[str, ModuleInfo],
    max_tokens: int,
    max_areas: int,
) -> dict[int, list[str]]:
    """Bisect oversized groups by sorted module token estimate."""
    next_id = (max(groups) + 1) if groups else 0
    changed = True
    while changed:
        changed = False
        if len(groups) >= max_areas:
            break
        for gid in list(groups):
            modules = groups[gid]
            if _group_tokens(modules, module_map) <= max_tokens or len(modules) < 2:
                continue
            sorted_mods = sorted(modules, key=lambda m: -module_map[m].token_estimate)
            mid = len(sorted_mods) // 2
            groups[gid] = sorted_mods[:mid]
            groups[next_id] = sorted_mods[mid:]
            next_id += 1
            changed = True
            break
    return groups


def _enforce_bounds(
    groups: dict[int, list[str]],
    adj: dict[str, set[str]],
    module_map: dict[str, ModuleInfo],
    min_areas: int,
    max_areas: int,
) -> dict[int, list[str]]:
    """Merge/split until group count is within [min_areas, max_areas]."""
    # Over limit → merge two smallest
    while len(groups) > max_areas:
        sorted_gids = sorted(groups, key=lambda g: _group_tokens(groups[g], module_map))
        smallest_gid = sorted_gids[0]
        second_gid = sorted_gids[1]
        groups[second_gid].extend(groups.pop(smallest_gid))

    # Under limit → split largest
    next_id = (max(groups) + 1) if groups else 0
    while len(groups) < min_areas:
        largest_gid = max(groups, key=lambda g: _group_tokens(groups[g], module_map))
        modules = groups[largest_gid]
        if len(modules) < 2:
            break  # cannot split a single module
        sorted_mods = sorted(modules, key=lambda m: -module_map[m].token_estimate)
        mid = len(sorted_mods) // 2
        groups[largest_gid] = sorted_mods[:mid]
        groups[next_id] = sorted_mods[mid:]
        next_id += 1

    return groups


# ---------------------------------------------------------------------------
# Area assembly
# ---------------------------------------------------------------------------

def _name_area(modules: list[str], module_map: dict[str, ModuleInfo]) -> str:
    """Human-readable name from the dominant top-level directory."""
    if len(modules) == 1:
        return modules[0].replace("/", " - ").title()

    dir_counts: dict[str, int] = {}
    for m in modules:
        d = module_map[m].top_dir
        dir_counts[d] = dir_counts.get(d, 0) + 1
    primary = max(dir_counts, key=dir_counts.get)  # type: ignore[arg-type]

    if len(dir_counts) == 1:
        return primary.replace("/", " - ").title()

    others = sorted(
        (d for d in dir_counts if d != primary),
        key=lambda d: -dir_counts[d],
    )[:2]
    return primary.title() + " & " + ", ".join(o.title() for o in others)


def _assemble_areas(
    groups: dict[int, list[str]],
    module_map: dict[str, ModuleInfo],
) -> list[DocumentationArea]:
    """Convert label groups into frozen ``DocumentationArea`` objects."""
    areas: list[DocumentationArea] = []
    for _gid, module_names in sorted(
        groups.items(),
        key=lambda item: -_group_tokens(item[1], module_map),
    ):
        all_files: list[tuple[str, int]] = []
        total_tokens = 0
        for m in module_names:
            mod = module_map[m]
            all_files.extend(mod.files)
            total_tokens += mod.token_estimate
        areas.append(DocumentationArea(
            name=_name_area(module_names, module_map),
            module_names=tuple(sorted(module_names)),
            files=tuple(all_files),
            token_estimate=total_tokens,
        ))
    return areas


# ---------------------------------------------------------------------------
# Single-area helper (no splitting)
# ---------------------------------------------------------------------------

def _single_area(analysis: RepoAnalysis) -> DocumentationArea:
    """Wrap the entire repository into one area (partitioning not warranted)."""
    all_modules = list(analysis.module_map.keys())
    all_files: list[tuple[str, int]] = []
    for mod in analysis.module_map.values():
        all_files.extend(mod.files)

    # Best-effort project name
    if analysis.module_count == 1:
        name = list(analysis.module_map.keys())[0]
    elif analysis.top_dirs:
        name = list(analysis.top_dirs.keys())[0].title()
    else:
        name = "Project"

    return DocumentationArea(
        name=name,
        module_names=tuple(sorted(all_modules)),
        files=tuple(all_files),
        token_estimate=analysis.token_estimate,
    )
