"""Permission checking — single pure function.

This is the ONE place where permission rules are defined. Adopters who want
a different permission model (e.g., deny lists, team-based access, time-based
grants) replace this function. Everything else in the system calls it.

Design:
    - Roles: admin > editor > viewer
    - Actions: read, edit, delete, admin
    - A user's grants are a list of (path_prefix, role) pairs
    - The most specific (longest) matching prefix determines the effective role
    - No matching grant = no access
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.user import FolderGrant

# Role → allowed actions mapping.
# Each role includes all actions of the roles below it.
_ROLE_ACTIONS: dict[str, set[str]] = {
    "admin": {"read", "edit", "delete", "admin"},
    "editor": {"read", "edit", "delete"},
    "viewer": {"read"},
}


def check_permission(
    grants: list[FolderGrant],
    doc_path: str,
    action: str,
) -> bool:
    """Check whether a user's grants allow *action* on *doc_path*.

    Finds the longest path_prefix in *grants* that matches *doc_path*,
    then checks whether the grant's role permits *action*.

    Args:
        grants: The user's folder grants (loaded once per request).
        doc_path: The document's ``path`` field (e.g. ``"crate/folder/doc"``).
        action: One of ``"read"``, ``"edit"``, ``"delete"``, ``"admin"``.

    Returns:
        True if permitted, False otherwise.
    """
    effective_role = resolve_role(grants, doc_path)
    if effective_role is None:
        return False
    return action in _ROLE_ACTIONS.get(effective_role, set())


def resolve_role(grants: list[FolderGrant], doc_path: str) -> str | None:
    """Find the effective role for a document path given a set of grants.

    Returns the role from the most specific (longest) matching grant,
    or None if no grant matches.
    """
    best_match_len = -1
    effective_role: str | None = None

    normalized_path = doc_path.strip("/")

    for grant in grants:
        prefix = grant.path_prefix.strip("/")

        # Empty prefix = root grant, matches everything
        if prefix == "":
            if best_match_len < 0:
                best_match_len = 0
                effective_role = grant.role
            continue

        # Check if document path is under this prefix
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            if len(prefix) > best_match_len:
                best_match_len = len(prefix)
                effective_role = grant.role

    return effective_role


def filter_paths_by_grants(
    grants: list[FolderGrant],
) -> list[str]:
    """Extract the list of accessible path prefixes from a user's grants.

    Used by repository queries to filter documents server-side.
    An empty string in the result means full access (root grant).
    """
    return [g.path_prefix.strip("/") for g in grants]
