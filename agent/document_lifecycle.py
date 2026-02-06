"""Document lifecycle operations: discovery, snapshots, regeneration context, cleanup.

Wraps all API-client interactions for document management.
Isolates network-dependent code from the rest of the pipeline.
"""

import logging
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from doc_registry import generate_doc_id
from prompts import CONTENT_SNIPPET_LENGTH, DOC_CONTEXT_LIMIT, GIT_DIFF_TRUNCATION
from security import PromptInjectionDetector

logger = logging.getLogger("isocrates.agent")


# ---------------------------------------------------------------------------
# Free function
# ---------------------------------------------------------------------------

def get_current_commit_sha(repo_path: Path) -> str:
    """Get current commit SHA of the repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


# ---------------------------------------------------------------------------
# DocumentLifecycle
# ---------------------------------------------------------------------------

class DocumentLifecycle:
    """API-facing document operations for discovery, snapshots, and cleanup.

    All network calls go through the injected *api_client*.
    """

    def __init__(
        self,
        api_client: object,
        repo_url: str,
        repo_path: Path,
        crate: str = "",
    ) -> None:
        self.api_client = api_client
        self.repo_url = repo_url
        self.repo_path = repo_path
        self.crate = crate

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> dict:
        """Query the API for existing documents (for cross-referencing)."""
        try:
            all_docs = self.api_client.get_all_documents()
            crate_prefix = self.crate.rstrip("/")
            related_docs = [
                doc
                for doc in all_docs
                if doc.get("path", "").startswith(crate_prefix)
            ] if crate_prefix else []
            return {
                "all_docs": all_docs,
                "related_docs": related_docs,
                "count": len(all_docs),
                "related_count": len(related_docs),
            }
        except Exception as e:
            logger.warning("Could not discover existing documents: %s", e)
            return {
                "all_docs": [],
                "related_docs": [],
                "count": 0,
                "related_count": 0,
            }

    def build_context(self, discovery: dict) -> str:
        """Format existing documents for inclusion in prompts."""
        if discovery["count"] == 0:
            return "\n**DOCUMENTATION ECOSYSTEM:** This is the first document in the system.\n"

        detector = PromptInjectionDetector()
        context = f"\n**DOCUMENTATION ECOSYSTEM:** {discovery['count']} existing documents.\n\n"
        context += "**Available documents for cross-referencing:**\n\n"

        by_crate = defaultdict(list)
        for doc in discovery["all_docs"]:
            path = doc.get("path", "")
            crate_name = path.split("/")[0] if "/" in path else "uncategorized"
            by_crate[crate_name].append(doc)

        for crate_name, docs in sorted(by_crate.items()):
            if crate_name:
                context += f"Crate: {detector.sanitize_filename(crate_name)}\n"
            for doc in docs[:DOC_CONTEXT_LIMIT]:
                title = doc.get("title", doc.get("repo_name", "Unknown"))
                safe = detector.sanitize_filename(title)
                dtype = doc.get("doc_type", "unknown")
                context += f"  - [[{safe}]] ({dtype})\n"
            if len(docs) > DOC_CONTEXT_LIMIT:
                context += f"  ... and {len(docs) - DOC_CONTEXT_LIMIT} more\n"
            context += "\n"
        return context

    # ------------------------------------------------------------------
    # Regeneration context
    # ------------------------------------------------------------------

    def get_regeneration_context(self) -> dict | None:
        """Check if docs exist for this repo and build a regen context.

        Returns ``None`` for first-time generation, or a dict with
        *last_commit_sha*, *existing_docs*, *git_diff*, *git_log*.
        """
        existing_list = self.api_client.get_documents_by_repo(self.repo_url)
        if not existing_list:
            return None

        print(f"[Regen] Found {len(existing_list)} existing doc(s) for this repo")

        existing_docs = []
        last_commit_sha = None
        for doc_summary in existing_list:
            doc_id = doc_summary.get("id")
            if not doc_id:
                continue
            full_doc = self.api_client.get_document(doc_id)
            if not full_doc:
                continue
            existing_docs.append({
                "id": doc_id,
                "title": full_doc.get("title", ""),
                "path": full_doc.get("path", ""),
                "doc_type": full_doc.get("doc_type", ""),
                "content": full_doc.get("content", ""),
            })

            if not last_commit_sha:
                versions = self.api_client.get_document_versions(doc_id)
                if versions:
                    meta = versions[0].get("author_metadata", {})
                    sha = meta.get("repo_commit_sha")
                    if sha and sha != "unknown":
                        last_commit_sha = sha

        if not existing_docs:
            return None

        git_diff = ""
        git_log = ""
        if last_commit_sha:
            print(f"[Regen] Last documented commit: {last_commit_sha[:8]}")
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--stat", f"{last_commit_sha}..HEAD"],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=30,
                )
                if diff_result.returncode == 0:
                    git_diff = diff_result.stdout

                detailed_diff = subprocess.run(
                    ["git", "diff", f"{last_commit_sha}..HEAD"],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=30,
                )
                if detailed_diff.returncode == 0 and detailed_diff.stdout.strip():
                    full_diff = detailed_diff.stdout
                    if len(full_diff) > GIT_DIFF_TRUNCATION:
                        git_diff += f"\n\n--- Detailed diff (truncated to {GIT_DIFF_TRUNCATION:,} chars) ---\n"
                        git_diff += full_diff[:GIT_DIFF_TRUNCATION] + "\n... [truncated]"
                    else:
                        git_diff += "\n\n--- Detailed diff ---\n" + full_diff

                log_result = subprocess.run(
                    ["git", "log", "--oneline", f"{last_commit_sha}..HEAD"],
                    cwd=self.repo_path,
                    capture_output=True, text=True, timeout=30,
                )
                if log_result.returncode == 0:
                    git_log = log_result.stdout
            except (subprocess.CalledProcessError, OSError) as e:
                logger.warning("Could not get git diff: %s", e)
        else:
            print("[Regen] No commit SHA found in existing docs, will do full re-exploration")
            return None

        if not git_diff.strip() and not git_log.strip():
            print("[Regen] No changes detected since last generation")
            return {
                "last_commit_sha": last_commit_sha,
                "existing_docs": existing_docs,
                "git_diff": "",
                "git_log": "",
            }

        print(f"[Regen] Changes detected:")
        print(f"   Commits since last gen: {len(git_log.strip().splitlines())}")
        print(f"   Diff size: {len(git_diff)} chars")

        return {
            "last_commit_sha": last_commit_sha,
            "existing_docs": existing_docs,
            "git_diff": git_diff,
            "git_log": git_log,
        }

    # ------------------------------------------------------------------
    # Snapshot & Cleanup
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Take a pre-generation snapshot of all docs belonging to this repo.

        Returns a dict with *doc_ids*, *by_id*, *human_edited*,
        *user_organized*, and *count*.
        """
        empty = {"doc_ids": set(), "by_id": {}, "human_edited": set(), "user_organized": set(), "count": 0}
        try:
            existing = self.api_client.get_documents_by_repo(self.repo_url)
            if not existing:
                return empty

            doc_ids: set[str] = set()
            by_id: dict[str, dict] = {}
            human_edited: set[str] = set()

            for doc in existing:
                doc_id = doc.get("id")
                if not doc_id:
                    continue
                doc_ids.add(doc_id)
                by_id[doc_id] = doc

                try:
                    versions = self.api_client.get_document_versions(doc_id)
                    for version in versions:
                        author_type = version.get("author_type", "")
                        if author_type == "human":
                            created = version.get("created_at", "")
                            if created:
                                version_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                age = datetime.now(timezone.utc) - version_dt
                                if age.days < 7:
                                    human_edited.add(doc_id)
                                    break
                except Exception:
                    logger.debug("Could not check versions for doc %s", doc_id)

            user_organized: set[str] = set()
            for doc_id in doc_ids:
                doc_info = by_id[doc_id]
                stored_path = doc_info.get("path", "")
                stored_title = doc_info.get("title", "")
                stored_doc_type = doc_info.get("doc_type", "")
                expected_id = generate_doc_id(self.repo_url, stored_path, stored_title, stored_doc_type)
                if expected_id != doc_id:
                    user_organized.add(doc_id)

            print(f"[Snapshot] {len(doc_ids)} existing doc(s) for this repo, "
                  f"{len(human_edited)} human-edited (7d), {len(user_organized)} user-organized")
            return {
                "doc_ids": doc_ids,
                "by_id": by_id,
                "human_edited": human_edited,
                "user_organized": user_organized,
                "count": len(doc_ids),
            }
        except Exception as e:
            logger.warning("Failed to snapshot existing docs: %s", e)
            return empty

    def cleanup_orphans(
        self,
        snapshot: dict,
        generated_ids: set,
        failed_ids: set,
    ) -> dict:
        """Delete orphaned AI-generated docs, preserving human-edited ones.

        SAFETY: Cleanup is skipped entirely when fewer than half of the
        attempted documents succeeded.  This prevents a failed generation
        run (bad API key, network outage, model error) from wiping out
        an entire documentation set.

        Returns a dict with *deleted*, *preserved_human*,
        *preserved_user_organized*, *preserved_failed*, *errors* counts.
        """
        result = {"deleted": 0, "preserved_human": 0, "preserved_user_organized": 0, "preserved_failed": 0, "errors": []}

        if not snapshot["doc_ids"]:
            print("[Cleanup] No snapshot — skipping orphan cleanup")
            return result

        # Circuit breaker: refuse to delete when the generation run
        # mostly failed.  A bad model config, revoked API key, or
        # network blip must NEVER destroy existing documentation.
        total_attempted = len(generated_ids) + len(failed_ids)
        if total_attempted == 0:
            print("[Cleanup] SAFETY: No documents were attempted — skipping orphan cleanup entirely")
            return result

        success_rate = len(generated_ids) / total_attempted
        if success_rate < 0.5:
            print(f"[Cleanup] SAFETY: Only {len(generated_ids)}/{total_attempted} documents succeeded "
                  f"({success_rate:.0%}) — skipping orphan cleanup to protect existing docs")
            return result

        orphans = snapshot["doc_ids"] - generated_ids - failed_ids
        if not orphans:
            print("[Cleanup] No orphaned documents found")
            return result

        human_edited = snapshot["human_edited"]
        user_organized = snapshot.get("user_organized", set())
        protected = human_edited | user_organized
        to_delete = orphans - protected
        preserved_human = orphans & human_edited
        preserved_user_org = orphans & user_organized - human_edited

        result["preserved_human"] = len(preserved_human)
        result["preserved_user_organized"] = len(preserved_user_org)
        result["preserved_failed"] = len(failed_ids & snapshot["doc_ids"])

        if preserved_human:
            for doc_id in preserved_human:
                title = snapshot["by_id"].get(doc_id, {}).get("title", doc_id)
                print(f"[Cleanup] Preserving human-edited: {title} ({doc_id})")

        if preserved_user_org:
            for doc_id in preserved_user_org:
                title = snapshot["by_id"].get(doc_id, {}).get("title", doc_id)
                print(f"[Cleanup] Preserving user-organized: {title} ({doc_id})")

        if not to_delete:
            reasons = []
            if preserved_human:
                reasons.append(f"{len(preserved_human)} human-edited")
            if preserved_user_org:
                reasons.append(f"{len(preserved_user_org)} user-organized")
            print(f"[Cleanup] {len(orphans)} orphan(s) found, all preserved ({', '.join(reasons) or 'protected'})")
            return result

        print(f"[Cleanup] Deleting {len(to_delete)} orphaned doc(s)...")
        for doc_id in to_delete:
            title = snapshot["by_id"].get(doc_id, {}).get("title", doc_id)
            print(f"   - {title} ({doc_id})")

        delete_result = self.api_client.batch_delete(list(to_delete))
        result["deleted"] = delete_result.get("succeeded", 0)
        result["errors"] = delete_result.get("errors", [])

        if result["errors"]:
            print(f"[Cleanup] Batch delete had errors: {result['errors']}")

        print(f"[Cleanup] Done: {result['deleted']} deleted, {result['preserved_human']} preserved (human), "
              f"{result['preserved_user_organized']} preserved (user-organized), {result['preserved_failed']} preserved (failed)")
        return result
