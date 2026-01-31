#!/usr/bin/env python3
"""
Autonomous Documentation Generator using OpenHands SDK

Leverages OpenHands' autonomous agent capabilities for deep codebase understanding:
- Multi-step exploration without human intervention
- Code execution and testing for runtime analysis
- Dynamic dependency tracing and architecture mapping
- Self-correction and iterative refinement

Usage:
    python openhands_doc.py --repo https://github.com/user/repo
    python openhands_doc.py --repo https://github.com/user/repo --collection backend/
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# OpenHands SDK imports
from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool

# Document registry for ID-based tracking
from doc_registry import (
    generate_doc_id,
    find_document_by_id,
    create_document_with_metadata,
    DocumentRegistry,
    parse_frontmatter,
    parse_bottomatter
)

# API client for posting to backend
from api_client import DocumentAPIClient

# Version priority logic for intelligent regeneration
from version_priority import VersionPriorityEngine

# Security modules
from security import RepositoryValidator, PathValidator


def clone_repo(repo_url: str, destination: Path) -> Path:
    """Clone or update a GitHub repository."""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = destination / repo_name

    if repo_path.exists():
        print(f"[Update] Updating: {repo_name}")
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=repo_path,
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError:
            print(f"[Warning]  Pull failed, using existing version")
    else:
        print(f"[Cloning] Cloning: {repo_url}")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(repo_path)],
            check=True,
            capture_output=True
        )

    return repo_path


class OpenHandsDocGenerator:
    """
    Autonomous documentation generator powered by OpenHands SDK.

    Uses OpenHands' multi-step reasoning and code execution capabilities
    to generate comprehensive, verified documentation.
    """

    def __init__(self, repo_path: Path, repo_url: str, collection: str = ""):
        self.repo_path = repo_path
        self.repo_url = repo_url
        self.repo_name = repo_path.name
        self.collection = collection + "/" if collection and not collection.endswith("/") else collection

        # Initialize document registry
        self.registry = DocumentRegistry()

        # Initialize API client
        self.api_client = DocumentAPIClient()

        # Load environment
        load_dotenv()

        # SECURITY: Load API key from Docker secrets file if available (production)
        # Falls back to environment variable for development
        api_key_file = os.getenv("OPENROUTER_API_KEY_FILE")
        if api_key_file and os.path.exists(api_key_file):
            with open(api_key_file) as f:
                self.api_key = f.read().strip()
        else:
            self.api_key = os.getenv("OPENROUTER_API_KEY")

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found (check environment or secrets file)")

        # Configure LLM
        self.llm = LLM(
            model="openrouter/mistralai/devstral-2512",  # Mistral coding agent via OpenRouter
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        # Configure Agent with restricted toolset
        # SECURITY NOTE: Agent capabilities are restricted via:
        # 1. Docker container hardening (see docker-compose.yml):
        #    - No privileged mode
        #    - Dropped capabilities (ALL)
        #    - Read-only workspace mount
        #    - Temp directory with noexec
        #    - Resource limits (4GB RAM, 200 PIDs)
        # 2. OpenHands SDK tool restrictions:
        #    - TerminalTool: Command execution in sandboxed environment
        #    - FileEditorTool: File operations within workspace only
        #    - No network tools or code execution tools
        # 3. Input validation (see main() function):
        #    - Repository URL whitelisting
        #    - Path traversal protection
        #    - Prompt injection sanitization
        self.agent = Agent(
            llm=self.llm,
            tools=[
                Tool(name=TerminalTool.name),      # Shell commands (sandboxed by Docker)
                Tool(name=FileEditorTool.name),    # File operations (workspace only)
                Tool(name=TaskTrackerTool.name),   # Track exploration progress
            ],
        )

        print(f"[Agent] OpenHands Agent Configured:")
        print(f"   Model: mistralai/devstral-2512 (via OpenRouter)")
        print(f"   Workspace: {self.repo_path}")
        print(f"   Tools: Terminal, FileEditor, TaskTracker")
        print(f"   Registry: ID-based document tracking enabled")

    def _discover_existing_documents(self) -> dict:
        """
        Query the API to discover existing documents.
        This allows the agent to create cross-references.

        Returns:
            dict with 'all_docs' (list of all documents) and 'related_docs' (docs in same collection)
        """
        try:
            # Get all documents
            all_docs = self.api_client.get_all_documents()

            # Filter to docs in same collection
            related_docs = [
                doc for doc in all_docs
                if doc.get('collection', '').rstrip('/') == self.collection.rstrip('/')
            ] if self.collection else []

            return {
                'all_docs': all_docs,
                'related_docs': related_docs,
                'count': len(all_docs),
                'related_count': len(related_docs)
            }
        except Exception as e:
            print(f"[Warning] Could not discover existing documents: {e}")
            return {
                'all_docs': [],
                'related_docs': [],
                'count': 0,
                'related_count': 0
            }

    def _build_document_context(self, discovery: dict) -> str:
        """
        Build context about existing documents for cross-referencing.
        """
        from security import PromptInjectionDetector

        if discovery['count'] == 0:
            return "\n**DOCUMENTATION ECOSYSTEM:** This is the first document in the system.\n"

        context = f"\n**DOCUMENTATION ECOSYSTEM:** The system contains {discovery['count']} existing documents.\n\n"

        # Initialize prompt safety detector
        detector = PromptInjectionDetector()

        # Group by collection
        from collections import defaultdict
        by_collection = defaultdict(list)
        for doc in discovery['all_docs']:
            collection = doc.get('collection', 'uncategorized')
            by_collection[collection].append(doc)

        context += "**Available documents for cross-referencing:**\n\n"
        for collection, docs in sorted(by_collection.items()):
            if collection:
                # SECURITY: Sanitize collection name
                safe_collection = detector.sanitize_filename(collection)
                context += f"Collection: {safe_collection}\n"
            for doc in docs[:10]:  # Limit to prevent prompt bloat
                doc_name = doc.get('repo_name', 'Unknown')
                # SECURITY: Sanitize document names to prevent prompt injection
                safe_doc_name = detector.sanitize_filename(doc_name)
                doc_type = doc.get('doc_type', 'unknown')
                context += f"  - [[{safe_doc_name}]] ({doc_type})\n"
            if len(docs) > 10:
                context += f"  ... and {len(docs) - 10} more\n"
            context += "\n"

        return context

    def _plan_document_tree(self, audience: str) -> list[dict]:
        """
        Plan a multi-page document tree by exploring the repository structure.

        Runs a lightweight agent conversation that analyzes the repo and produces
        a list of pages to generate. Each page has a path, title, and doc_type.

        Args:
            audience: "client" or "softdev" — determines page structure

        Returns:
            List of page descriptors: [{path, title, doc_type, description}]
            Minimum 4 pages for non-trivial repos.
        """
        import json

        crate_path = f"{self.collection}{self.repo_name}".rstrip('/')

        planning_prompt = f"""You are a documentation planning agent. Analyze the repository at {self.repo_path} and produce a JSON document tree.

AUDIENCE: {"Business stakeholders (non-technical)" if audience == "client" else "Software developers and technical teams"}

TASK: Explore the repository structure (README, source files, tests, configs) and decide what documentation pages to create. Output a JSON array of page descriptors.

RULES:
- Produce at least 4 pages, at most 8
- Each page must have a distinct focus — no overlap
- The first page should be the main overview/reference
- All pages share the crate path: "{crate_path}"

{"CLIENT PAGES should cover: Executive Summary, Features & Capabilities, Use Cases, Integration Guide" if audience == "client" else "SOFTDEV PAGES should cover: Technical Reference (overview), Getting Started, API Reference, Architecture Deep Dive. Add more if the repo warrants it (e.g., Testing Guide, Configuration, Advanced Patterns)."}

OUTPUT FORMAT (JSON only, no markdown wrapping):
[
  {{"path": "{crate_path}", "title": "Technical Reference", "doc_type": "{audience}", "description": "Main overview of the project"}},
  {{"path": "{crate_path}", "title": "Getting Started", "doc_type": "{audience}", "description": "Setup and first steps"}},
  ...
]

Use terminal commands (ls, cat, find, tree) to explore the repo, then output ONLY the JSON array to /tmp/doc_tree.json
"""

        try:
            conversation = Conversation(
                agent=self.agent,
                workspace=str(self.repo_path)
            )
            conversation.send_message(planning_prompt)
            conversation.run()

            # Read the planned tree
            tree_file = Path("/tmp/doc_tree.json")
            if tree_file.exists():
                tree = json.loads(tree_file.read_text())
                if isinstance(tree, list) and len(tree) >= 2:
                    print(f"[Planning] Document tree planned: {len(tree)} pages")
                    for page in tree:
                        print(f"   - {page.get('title', 'Untitled')}: {page.get('description', '')}")
                    return tree

            print("[Planning] Agent did not produce a valid tree, using default structure")
        except Exception as e:
            print(f"[Planning] Planning failed ({e}), using default structure")

        # Fallback: default 4-page structure
        if audience == "client":
            return [
                {"path": crate_path, "title": "Business Overview", "doc_type": "client", "description": "Executive summary and business value"},
                {"path": crate_path, "title": "Features and Capabilities", "doc_type": "client", "description": "Key features explained for business audience"},
                {"path": crate_path, "title": "Use Cases", "doc_type": "client", "description": "Real-world applications and scenarios"},
                {"path": crate_path, "title": "Integration Guide", "doc_type": "client", "description": "How to adopt and integrate"},
            ]
        else:
            return [
                {"path": crate_path, "title": "Technical Reference", "doc_type": "softdev", "description": "Architecture and design overview"},
                {"path": crate_path, "title": "Getting Started", "doc_type": "softdev", "description": "Setup, installation, and first steps"},
                {"path": crate_path, "title": "API Reference", "doc_type": "softdev", "description": "Endpoints, functions, and interfaces"},
                {"path": crate_path, "title": "Architecture Deep Dive", "doc_type": "softdev", "description": "System design, data flow, and patterns"},
            ]

    def _build_task_prompt(self, doc_type: str, discovery: dict = None, sibling_pages: list[dict] = None) -> str:
        """Build comprehensive task prompt for autonomous documentation generation."""

        output_path = Path("/notes") / f"{self.collection}{self.repo_name}-{doc_type}.md"

        # Discover existing documents if not provided
        if discovery is None:
            discovery = self._discover_existing_documents()

        base_context = f"""
You are an autonomous software analysis agent. Your mission is to deeply understand the codebase at:
{self.repo_path}

EXPLORATION STRATEGY:
1. **Initial Survey**
   - Read README.md, LICENSE, and top-level documentation
   - Identify project metadata (package.json, setup.py, Cargo.toml, go.mod, etc.)
   - Determine primary language(s), framework(s), and dependencies

2. **Architecture Mapping**
   - Find entry points (main.py, index.js, cmd/main.go, etc.)
   - Map directory structure and module organization
   - Identify core components and their responsibilities
   - Trace data models, schemas, and persistence layers
   - Document external dependencies and integrations

3. **Code Analysis** (Static Analysis Only - DO NOT Execute Code!)
   - READ test files to understand what's being tested
   - READ example scripts to understand usage patterns
   - Trace imports and dependencies through the code
   - Infer behavior from code structure and patterns
   - READ error handling code to understand edge cases
   - Use grep/find to map relationships between files

4. **Code Quality Assessment**
   - Evaluate project structure and organization
   - Assess testing approach by READING test files
   - Review documentation completeness
   - Identify security patterns and considerations

AUTONOMOUS OPERATION:
- You have FULL autonomy to READ and EXPLORE
- Use terminal ONLY for: ls, cat, grep, find, tree, git log (read-only commands)
- DO NOT run tests, execute scripts, or start applications
- DO NOT use: python script.py, npm test, cargo run, etc.
- Think of this as code review/onboarding - you're reading, not executing
- Read any file you need
- Self-correct and iterate until you have complete understanding

DOCUMENTATION ECOSYSTEM AWARENESS:
- You are part of a larger documentation system with multiple interconnected documents
- Use [[WikiLink]] syntax liberally to reference other documents, concepts, and technologies
- Think of this as building a knowledge graph, not isolated documentation
- Every mention of a technology, pattern, or concept is an opportunity to create a link
- Your documentation should naturally guide readers to related content
"""

        # Build document context from discovery
        doc_context = self._build_document_context(discovery)

        # Build sibling pages context for multi-page generation
        sibling_context = ""
        if sibling_pages:
            sibling_context = "\n**SIBLING PAGES IN THIS DOCUMENT SET:**\n"
            sibling_context += "You are generating one page of a multi-page documentation set. The other pages are:\n\n"
            for page in sibling_pages:
                sibling_context += f"  - [[{page['title']}]]: {page.get('description', '')}\n"
            sibling_context += "\nUse [[Page Title]] wikilinks to reference sibling pages throughout your content.\n"
            sibling_context += "Do NOT duplicate content covered by sibling pages — instead link to them.\n\n"

        if doc_type == "client":
            audience_spec = f"""
TARGET AUDIENCE: Non-technical business stakeholders

{doc_context}
{sibling_context}

RICH CONTENT — TABLES ONLY:
Use GFM tables for summary comparisons, feature matrices, and requirement lists.
Do NOT use mermaid diagrams — keep content accessible for business readers.
MINIMUM: At least 1 summary table in the document.

Example:
| Feature | Description | Business Impact |
|---------|-------------|-----------------|
| Auto-sync | Real-time data updates | Reduces manual effort by 80% |

OUTPUT DOCUMENT STRUCTURE:
# {Project Name} - Business Overview

## Executive Summary
Write a comprehensive paragraph that flows naturally, explaining what this project does and why it exists. Use narrative style, not lists.

## Purpose & Problem Statement
Write flowing prose that describes the business problem this solves. Connect ideas with transitions. Tell a story about the need this addresses.

## Key Features
WRITE ONLY IN PARAGRAPHS. DO NOT USE BULLET POINTS, DASHES, OR LISTS. Describe each feature in complete sentences within flowing paragraphs. For example: "The system provides comprehensive option pricing capabilities that accurately value various types of options. These include vanilla European options, American options with early exercise features, and exotic variants such as digital options and barrier products." Continue this narrative style throughout.

## Use Cases & Applications
Write narrative paragraphs describing who uses this and what scenarios it's designed for. Make it read like an article, not a list.

## Integration & Deployment
Explain deployment in prose format - how someone would use or deploy this, written as flowing explanatory text.

## Business Value & ROI
Write compelling paragraphs about the value proposition. Make it persuasive prose, not bullet points.

## Technical Requirements (Simplified)
Describe technical requirements in simple paragraph form, suitable for business readers.

## Related Documentation
If this project integrates with or relates to other documented systems, reference them using wikilink syntax. For example: "This system integrates with [[SystemName]] to provide..." or "For technical implementation details, see [[ProjectName - Technical Reference]]."

CROSS-REFERENCING GUIDELINES:
- Use [[Document Name]] syntax to link to other documents in the system
- Link to related business capabilities, systems, or technologies
- Reference prerequisite knowledge (e.g., "requires understanding of [[ConceptName]]")
- Create natural connections in flowing prose (don't list links separately)
- If mentioning a technology/library that has docs, link it: [[LibraryName]]

CRITICAL STYLE REQUIREMENTS (ABSOLUTELY MANDATORY):

You must write in flowing prose paragraphs only. Never use bullet points, dashes, asterisks, or numbered lists anywhere in the document. Every section must contain at least two to four flowing paragraphs that read smoothly with transition words connecting ideas. Use words like however, moreover, additionally, and furthermore to link sentences. If you find yourself about to write a dash or bullet point, stop immediately and rewrite that content as complete sentences within a paragraph instead.

Write in simple, accessible language suitable for a general audience. Do not include code snippets or emojis. The final document should read like a New York Times business article or a Harvard Business Review piece, with each idea flowing naturally into the next through well-constructed paragraphs.
"""
        else:  # softdev
            audience_spec = f"""
TARGET AUDIENCE: Software developers and technical teams

{doc_context}
{sibling_context}

RICH CONTENT REQUIREMENTS (MANDATORY):

1. GFM Tables: Use GitHub-Flavored Markdown tables for:
   - API endpoint summaries (method, path, description, auth required)
   - Configuration option lists (option, type, default, description)
   - Comparison matrices (feature vs feature)
   - Dependency lists (package, version, purpose)
   Example:
   | Endpoint | Method | Description |
   |----------|--------|-------------|
   | /api/users | GET | List all users |
   | /api/users | POST | Create a user |

2. Mermaid Diagrams: Use ```mermaid blocks for:
   - Component/architecture diagrams (graph TD)
   - Data flow diagrams (flowchart LR)
   - State machines (stateDiagram-v2)
   - Sequence diagrams for key interactions
   Example:
   ```mermaid
   graph TD
     A[Client] --> B[API Gateway]
     B --> C[Service Layer]
     C --> D[Database]
   ```

MINIMUM: The document MUST contain at least 1 GFM table AND at least 1 mermaid diagram.

OUTPUT DOCUMENT STRUCTURE:
# {Project Name} - Technical Reference

## Overview
Write a flowing technical narrative describing the architecture and design philosophy. Use paragraphs, not bullet points.

## Technology Stack
Describe the technology choices in paragraph form. Explain what languages, frameworks, and infrastructure are used, weaving this into coherent prose rather than lists.

## Architecture
### System Design
Write detailed paragraphs describing the main components and how they interact. Use flowing prose to explain the architecture.

### Data Flow
Explain in narrative form how data moves through the system - from requests through processing to storage. Make it read like technical documentation prose.

### Key Design Decisions
Write paragraphs explaining why certain frameworks were chosen, what architectural patterns are used, and the trade-offs involved. Connect these ideas with transitions.

## API Reference
Provide code examples in blocks, but explain them with surrounding prose. Describe endpoints or functions in paragraph form before showing code.

Example structure:
The system exposes several REST endpoints for resource management. The primary endpoint handles...

```
GET /api/v1/resource
POST /api/v1/resource
```

## Development Setup
Explain the setup process in flowing text, then provide code blocks. Don't just list commands - explain what they do.

The development environment requires cloning the repository and installing dependencies. First, developers should...

```bash
git clone {repo_url}
cd {repo_name}
```

## Testing
Describe the testing approach in paragraph form. Explain what framework is used, the testing philosophy, and coverage details as flowing prose.

## Code Quality Assessment
Write comprehensive paragraphs evaluating structure, testing, documentation, security, and performance. Make it read like a code review report, not a checklist.

## Deployment
Explain the deployment strategy in narrative form, describing the production setup and configuration.

## Known Issues & Limitations
Describe limitations in honest, flowing prose. Explain context and implications.

## Related Documentation & Cross-References
This section is CRITICAL for building an interconnected documentation graph. Link to related documents, dependencies, and concepts throughout the documentation.

CROSS-REFERENCING STRATEGY (EXTREMELY IMPORTANT):

1. **Technology Dependencies**: When mentioning frameworks, libraries, or technologies that have their own documentation in the system, link them:
   - "uses [[Redis]] for caching"
   - "built on top of [[FastAPI]] framework"
   - "integrates with [[PostgreSQL]] for persistence"

2. **Related Projects**: If this project is part of a larger ecosystem or relates to other documented projects:
   - "complements the [[FrontendService]] by providing..."
   - "shares architecture patterns with [[SimilarProject]]"
   - "serves as the backend for [[ClientApplication]]"

3. **Conceptual Links**: Reference architectural concepts, design patterns, or technical approaches:
   - "implements the [[Repository Pattern]]"
   - "follows [[Microservices Architecture]] principles"
   - "uses [[Event Sourcing]] for state management"

4. **Hierarchical Structure**: For complex projects, suggest creating separate deep-dive documents:
   - Main overview (this document) links to:
     - "[[{self.repo_name} - Getting Started]]" (beginner guide)
     - "[[{self.repo_name} - Core Concepts]]" (intermediate concepts)
     - "[[{self.repo_name} - API Reference]]" (exhaustive reference)
     - "[[{self.repo_name} - Advanced Patterns]]" (expert techniques)
     - "[[{self.repo_name} - Architecture Deep Dive]]" (system design)

5. **Progressive Disclosure**: Structure content from simple to complex:
   - Overview → Basics → Intermediate → Advanced → Expert
   - Each level links to the next: "For advanced usage patterns, see [[{self.repo_name} - Advanced Patterns]]"

6. **Bidirectional Linking**: Create connections that work both ways:
   - Prerequisites: "Requires understanding of [[ConceptX]]"
   - Extensions: "For database integration, see [[DatabaseModule]]"
   - Alternatives: "Compare with [[AlternativeApproach]]"

WIKILINK SYNTAX: Use [[Document Name]] throughout the text. The system will automatically resolve these to actual documents.

EXAMPLES OF GOOD CROSS-REFERENCING:
- "The authentication module integrates with [[OAuth2Provider]] and supports [[JWT]] tokens as described in the [[Security Architecture]] documentation."
- "This service follows the [[Clean Architecture]] pattern, with clear separation between domain logic and infrastructure concerns as outlined in [[DomainDrivenDesign]]."
- "For performance optimization, the system employs [[Redis]] caching and [[PostgreSQL]] connection pooling, with monitoring provided by [[PrometheusMetrics]]."

CRITICAL STYLE REQUIREMENTS (ABSOLUTELY MANDATORY):

Write all explanations in flowing paragraph form without using bullet points, dashes, asterisks, or numbered lists for descriptions. Code blocks are acceptable for examples, but you must surround them with explanatory prose paragraphs. Use transition words like however, additionally, and furthermore to connect ideas smoothly. When describing multiple items, write them within a paragraph using formats like "The system includes X, Y, and Z" rather than listing them separately.

Maintain technical precision while using narrative paragraph style throughout. The documentation should read like a Martin Fowler blog post or an O'Reilly technical article, prioritizing flowing readability over terse lists. Every technical concept should be explained through well-constructed sentences that build on each other logically.
"""

        task_description = f"""
{base_context}

{audience_spec}

OUTPUT REQUIREMENTS:
- Write the COMPLETE markdown document to: {output_path}
- Ensure the file is comprehensive and well-structured
- Base everything on verified facts (code you read, tests you ran)
- If tests fail, document it honestly
- Include actual commands and outputs you verified

CROSS-REFERENCE CHECKLIST (Review before finalizing):
1. Have you mentioned any technologies/frameworks? → Add [[TechnologyName]] links
2. Does this project integrate with other systems? → Link them with [[SystemName]]
3. Are there related concepts worth exploring? → Add [[ConceptName]] references
4. Should this be split into multiple documents? → Suggest hierarchical structure
5. Review the "Available documents for cross-referencing" list above → Link relevant ones

WIKILINK EXAMPLES:
- Technology: "built with [[FastAPI]] and [[React]]"
- Integration: "connects to [[DatabaseService]] for persistence"
- Concept: "follows [[Clean Architecture]] principles"
- Hierarchy: "For setup instructions, see [[{self.repo_name} - Getting Started]]"

CRITICAL:
- Work AUTONOMOUSLY - don't ask permission
- Explore as deeply as needed
- Run commands to verify claims
- ADD CROSS-REFERENCES throughout the document
- Generate the complete document with wikilinks
- Save to {output_path} when done

When complete, confirm the file was written and summarize:
1. How many wikilinks you added
2. What documents/concepts you referenced
3. Whether you recommend creating additional hierarchical documents
"""

        return task_description

    def _archive_version(self, doc_path: Path, doc_id: str):
        """
        Archive the current version of a document before regenerating.

        Creates: /notes/.history/{doc_id}/{timestamp}.md
        """
        from datetime import datetime
        import shutil

        # Create history directory (visible, not hidden)
        history_dir = Path("/notes/history") / doc_id
        history_dir.mkdir(parents=True, exist_ok=True)

        # Read current content and extract metadata
        content = doc_path.read_text()
        metadata, _ = parse_frontmatter(content)

        # Use the generated_at timestamp from frontmatter if available
        if metadata and 'generated_at' in metadata:
            timestamp = metadata['generated_at'].replace(':', '-').replace('.', '-')
        else:
            timestamp = datetime.utcnow().isoformat().replace(':', '-').replace('.', '-')

        # Archive file
        archive_path = history_dir / f"{timestamp}.md"
        shutil.copy2(doc_path, archive_path)

        print(f"[Archive] Archived previous version to: {archive_path}")

    def _update_version_index(self, doc_id: str, doc_type: str):
        """
        Create/update version history index page.

        Creates: /notes/{repo_name}-{doc_type}-history.md
        """
        from datetime import datetime

        history_dir = Path(f"/notes/history/{doc_id}")

        if not history_dir.exists():
            return

        # List all archived versions
        versions = sorted(history_dir.glob("*.md"), key=lambda p: p.stem, reverse=True)

        if not versions:
            return

        # Create index page
        index_content = f"""---
id: {doc_id}-history
doc_id: {doc_id}
repo_name: {self.repo_name}
doc_type: {doc_type}
page_type: version-history
---

# Version History: {self.repo_name} ({doc_type})

This page lists all generated versions of the **{self.repo_name} {doc_type}** documentation.

## Available Versions

"""

        for version_file in versions:
            # Parse timestamp from filename
            timestamp_str = version_file.stem
            try:
                # Convert ISO format timestamp (handle the extra precision)
                # Format: 2026-01-29T11-10-49-656819
                parts = timestamp_str.split('T')
                date_part = parts[0]
                time_part = parts[1].replace('-', ':')
                # Reconstruct with colons for time
                iso_str = f"{date_part}T{time_part}"
                dt = datetime.fromisoformat(iso_str)
                display_time = dt.strftime("%d %B %Y at %I:%M%p")
            except Exception as e:
                # Fallback to raw timestamp
                display_time = timestamp_str

            # Create SilverBullet wikilink to version
            # Use absolute path from /notes root
            page_name = f"history/{doc_id}/{version_file.stem}"
            index_content += f"- [[{page_name}|{display_time}]]\n"

        index_content += f"""

## Current Version

The current version is available at: [[{self.repo_name}-{doc_type}]]

---

*Version history is automatically maintained. Each time documentation is regenerated, the previous version is archived here.*
"""

        # Write index page
        index_path = Path(f"/notes/{self.collection}{self.repo_name}-{doc_type}-history.md")
        index_path.write_text(index_content)

        print(f"[Index] Updated version history index: {index_path}")

    def _get_current_commit_sha(self) -> str:
        """Get current commit SHA of the repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"
        except Exception:
            return "unknown"

    def generate_documentation(self, doc_type: str, path: str = "", title: str = "", sibling_pages: list[dict] = None) -> dict:
        """
        Generate documentation using OpenHands autonomous agent.

        Args:
            doc_type: Document type (client, softdev, or hierarchical type)
            path: Folder path (e.g., "User Guide/Advanced")
            title: Document title (e.g., "Async Patterns")

        Returns:
            Dictionary with status, output file path, and document ID
        """
        # Auto-derive title from doc_type if not provided (for backward compatibility)
        if not title:
            title = doc_type.replace('-', ' ').title()

        # Generate stable document ID using new format
        doc_id = generate_doc_id(self.repo_url, path, title, doc_type)

        print(f"\n{'='*70}")
        print(f"[Starting] STARTING {doc_type.upper()} DOCUMENTATION GENERATION")
        print(f"{'='*70}\n")
        print(f"[Doc] Document ID: {doc_id}")

        # Get current commit SHA for version tracking
        current_commit_sha = self._get_current_commit_sha()

        # Check version priority - should we regenerate?
        priority_engine = VersionPriorityEngine(
            api_client=self.api_client,
            repo_path=self.repo_path
        )

        should_generate, reason = priority_engine.should_regenerate(
            doc_id=doc_id,
            current_commit_sha=current_commit_sha
        )

        if not should_generate:
            print(f"\n[Skip] {reason}")
            print(f"{'='*70}\n")
            return {
                "status": "skipped",
                "reason": reason,
                "doc_id": doc_id
            }

        print(f"\n[Generate] {reason}")
        print(f"{'='*70}\n")

        # Discover existing documents for cross-referencing
        print(f"[Discovery] Discovering existing documents for cross-referencing...")
        discovery = self._discover_existing_documents()
        print(f"   Found {discovery['count']} documents in the system")
        if discovery['related_count'] > 0:
            print(f"   {discovery['related_count']} in same collection: {self.collection}")
        if discovery['count'] > 0:
            print(f"   Agent will be instructed to create [[wikilinks]] to related docs")
        print()

        # Check if document already exists (by ID, not filename)
        existing_doc_path = find_document_by_id(doc_id)
        if existing_doc_path:
            print(f"[Regenerate]  Existing document found: {existing_doc_path}")
            print(f"   Regenerating documentation (will update existing file)\n")

            # Archive old version
            self._archive_version(existing_doc_path, doc_id)

        try:
            # Create conversation with agent
            conversation = Conversation(
                agent=self.agent,
                workspace=str(self.repo_path)
            )

            # Build task prompt with discovery context and sibling pages
            task_prompt = self._build_task_prompt(doc_type, discovery, sibling_pages)

            print(f"[Task] Task Assigned:")
            print(f"   Type: {doc_type}")
            print(f"   Workspace: {self.repo_path}")
            print(f"   Output: /notes/{self.collection}{self.repo_name}-{doc_type}.md\n")

            print(f"[Agent] Agent starting autonomous exploration...")
            print(f"   (This may take several minutes)\n")

            # Send task and run autonomously
            conversation.send_message(task_prompt)
            conversation.run()  # Fully autonomous execution

            # Check results
            output_file = Path(f"/notes/{self.collection}{self.repo_name}-{doc_type}.md")

            if output_file.exists():
                # Read the generated content
                raw_content = output_file.read_text()

                # Strip old metadata (try bottomatter first, then frontmatter)
                import re
                metadata, body = parse_bottomatter(raw_content)
                if not metadata:
                    metadata, body = parse_frontmatter(raw_content)

                # Strip any old header timestamps
                header_pattern = r'^\*Documentation Written by.*?\*\n+'
                body = re.sub(header_pattern, '', body)

                # Strip old footers (everything after "Documentation Written")
                footer_pattern = r'\n---\n\n\*Documentation.*$'
                clean_content = re.sub(footer_pattern, '', body, flags=re.DOTALL)

                # T2: Verify rich content presence (non-blocking)
                has_table = '|' in clean_content and '---' in clean_content
                has_mermaid = '```mermaid' in clean_content
                if doc_type == "softdev":
                    if not has_table:
                        print("[Content] Warning: softdev doc missing GFM tables")
                    if not has_mermaid:
                        print("[Content] Warning: softdev doc missing mermaid diagrams")
                elif doc_type == "client":
                    if not has_table:
                        print("[Content] Warning: client doc missing GFM tables")

                # Get commit SHA for version tracking
                commit_sha = self._get_current_commit_sha()

                # Prepare API payload with new hierarchical fields
                doc_data = {
                    "repo_url": self.repo_url,
                    "repo_name": self.repo_name,
                    "collection": self.collection.rstrip('/'),
                    "path": path,  # Folder path for hierarchical organization
                    "title": title,  # Document title
                    "doc_type": doc_type,  # Legacy field for backward compatibility
                    "content": clean_content,  # Clean content WITHOUT header/footer
                    "author_type": "ai",
                    "author_metadata": {
                        "generator": "openhands-autonomous-agent",
                        "model": "mistralai/devstral-2512",
                        "agent": "openhands-autonomous",
                        "repo_commit_sha": commit_sha
                    }
                }

                # Try to POST to API first
                try:
                    print(f"\n[API] Posting document to backend API...")
                    api_result = self.api_client.create_or_update_document(
                        doc_data=doc_data,
                        fallback_path=output_file
                    )

                    content_preview = clean_content[:500]
                    content_size = len(clean_content.encode('utf-8'))

                    if api_result.get("method") == "filesystem":
                        # API failed, used fallback
                        print(f"\n[Fallback] Document saved to file (API unavailable)")
                        print(f"   ID: {doc_id}")
                        print(f"   File: {output_file}")
                    else:
                        # API success
                        print(f"\n[Success] DOCUMENTATION POSTED TO API SUCCESSFULLY!")
                        print(f"   ID: {api_result.get('id', doc_id)}")
                        print(f"   Status: {api_result.get('status', 'created')}")

                    print(f"   Size: {content_size:,} bytes")
                    print(f"   Preview: {content_preview[:200]}...\n")

                    # Register in document registry (for local tracking)
                    if existing_doc_path:
                        self.registry.update_document(doc_id, str(output_file))
                    else:
                        self.registry.register_document(
                            doc_id=doc_id,
                            repo_url=self.repo_url,
                            doc_type=doc_type,
                            file_path=str(output_file),
                            metadata={"collection": self.collection.rstrip('/')}
                        )

                    return {
                        "status": "success",
                        "doc_id": api_result.get('id', doc_id),
                        "method": api_result.get("method", "api"),
                        "size": content_size,
                        "preview": content_preview,
                        "api_result": api_result
                    }

                except Exception as e:
                    # Complete failure - log and return error
                    print(f"\n[Error] Failed to post document: {e}")
                    print(f"   Saving to file as emergency fallback...")

                    # Emergency fallback - write with metadata
                    from datetime import datetime
                    now = datetime.now()
                    timestamp = now.strftime("%d/%m/%Y at %I:%M%p")
                    header = f"*Documentation Written by IsoCrates on {timestamp}*\n\n"
                    content_with_header = header + clean_content

                    content_with_metadata = create_document_with_metadata(
                        content=content_with_header,
                        doc_id=doc_id,
                        repo_url=self.repo_url,
                        doc_type=doc_type,
                        collection=self.collection.rstrip('/'),
                        additional_metadata={
                            "agent": "openhands-autonomous",
                            "model": "mistralai/devstral-2512",
                            "repo_commit_sha": commit_sha
                        }
                    )

                    output_file.write_text(content_with_metadata)

                    return {
                        "status": "error_fallback",
                        "doc_id": doc_id,
                        "error": str(e),
                        "file": str(output_file)
                    }
            else:
                print(f"\n[Warning]  WARNING: Output file not found at {output_file}")
                print(f"   Agent may have encountered issues")
                print(f"   Check conversation logs for details\n")
                return {
                    "status": "warning",
                    "message": "File not found at expected location",
                    "expected_file": str(output_file)
                }

        except Exception as e:
            print(f"\n[Error] ERROR DURING GENERATION: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e)
            }

    def generate_all(self) -> dict:
        """
        Generate multi-page documentation for both client and developer audiences.

        Plans a document tree per audience, then generates each page with
        cross-references to sibling pages via wikilinks.
        """
        results = {}

        print("\n" + "="*70)
        print("[Target] GENERATING MULTI-PAGE DOCUMENTATION SET")
        print("="*70)

        for audience_idx, audience in enumerate(["client", "softdev"], 1):
            print(f"\n[{audience_idx}/2] Planning {audience} documentation tree...")
            doc_tree = self._plan_document_tree(audience)

            total_pages = len(doc_tree)
            for page_idx, page in enumerate(doc_tree, 1):
                # Build sibling list (all pages except the current one)
                siblings = [p for p in doc_tree if p["title"] != page["title"]]

                print(f"\n[{audience_idx}/2 - {page_idx}/{total_pages}] Generating: {page['title']}")
                result = self.generate_documentation(
                    doc_type=page["doc_type"],
                    path=page["path"],
                    title=page["title"],
                    sibling_pages=siblings
                )
                results[f"{audience}-{page['title']}"] = result

        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate documentation using OpenHands autonomous agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo https://github.com/facebook/react
  %(prog)s --repo https://github.com/django/django --collection backend
        """
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository URL"
    )
    parser.add_argument(
        "--collection",
        default="",
        help="Optional collection prefix (e.g., 'backend' → backend/repo-name-client.md)"
    )
    parser.add_argument(
        "--doc-type",
        choices=["client", "softdev", "both"],
        default="both",
        help="Type of documentation to generate (default: both)"
    )
    args = parser.parse_args()

    # SECURITY: Validate repository URL
    validator = RepositoryValidator()
    is_valid, error, sanitized_url = validator.validate_repo_url(args.repo)
    if not is_valid:
        print(f"[Security] Repository URL validation failed: {error}")
        print(f"[Security] Provided URL: {args.repo}")
        sys.exit(1)

    # SECURITY: Validate collection path
    path_validator = PathValidator()
    is_valid, error, sanitized_collection = path_validator.validate_collection(args.collection)
    if not is_valid:
        print(f"[Security] Collection validation failed: {error}")
        print(f"[Security] Provided collection: {args.collection}")
        sys.exit(1)

    print("="*70)
    print("[Agent] OPENHANDS AUTONOMOUS DOCUMENTATION GENERATOR")
    print("="*70)
    print(f"Repository: {sanitized_url}")
    if sanitized_collection:
        print(f"Collection: {sanitized_collection}")
    print()

    # Clone repository
    repos_dir = Path("/repos")
    repos_dir.mkdir(exist_ok=True)

    try:
        # Use sanitized URL
        repo_path = clone_repo(sanitized_url, repos_dir)
    except subprocess.CalledProcessError as e:
        print(f"[Error] Failed to clone repository: {e}")
        sys.exit(1)

    # Generate documentation with sanitized inputs
    generator = OpenHandsDocGenerator(repo_path, sanitized_url, sanitized_collection)

    if args.doc_type == "both":
        results = generator.generate_all()
    else:
        results = {args.doc_type: generator.generate_documentation(args.doc_type)}

    # Summary
    print("\n" + "="*70)
    print("[Summary] GENERATION SUMMARY")
    print("="*70)

    for doc_type, result in results.items():
        print(f"\n{doc_type.upper()}:")
        if result["status"] == "success":
            print(f"  [Success] Success")
            print(f"  [ID] ID: {result['doc_id']}")
            print(f"  [Method] {result.get('method', 'api').upper()}")
            if 'file' in result:
                print(f"  [File] File: {result['file']}")
            print(f"  [Size] Size: {result['size']:,} bytes")
        elif result["status"] == "warning":
            print(f"  [Warning]  Warning: {result['message']}")
        else:
            print(f"  [Error] Error: {result.get('error', 'Unknown error')}")

    print("\n[Info] Documentation available at:")
    print("   API: http://localhost:8000/api/docs")
    print("   Frontend: http://localhost:3000\n")


if __name__ == "__main__":
    main()
