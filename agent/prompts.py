"""Prompt templates, document taxonomy, and pipeline constants.

This module contains all static data used across the agent pipeline:
prompt fragments, scout definitions, focus patterns, and tuning constants.
No runtime logic — pure data only.
"""

import re

# ---------------------------------------------------------------------------
# Document Type Taxonomy (used for fallback and keyword tagging only —
# the planner is free to create any page structure it wants)
# ---------------------------------------------------------------------------

DOCUMENT_TYPES: dict[str, dict[str, object]] = {
    "quickstart": {"title": "Quick Start", "keywords": ["Getting Started", "Installation"]},
    "overview": {"title": "Overview", "keywords": ["Overview", "Introduction"]},
    "architecture": {"title": "Architecture", "keywords": ["Architecture", "Design"]},
    "api": {"title": "API", "keywords": ["API", "Reference", "Endpoints"]},
    "guide": {"title": "Guide", "keywords": ["Guide", "How-To"]},
    "config": {"title": "Configuration", "keywords": ["Configuration", "Deployment"]},
    "component": {"title": "Component", "keywords": ["Component", "Module"]},
    "data-model": {"title": "Data Model", "keywords": ["Data", "Schema", "Model"]},
    "contributing": {"title": "Contributing", "keywords": ["Contributing", "Development"]},
    "capabilities": {"title": "Capabilities & User Stories", "keywords": ["Capabilities", "User Stories", "Features", "Use Cases"]},
}

COMPLEXITY_ORDER: dict[str, int] = {"small": 0, "medium": 1, "large": 2}

# ---------------------------------------------------------------------------
# Agent Pipeline Constants
# ---------------------------------------------------------------------------
# Condenser sizing: context_window is divided by these values to determine
# how many conversation events to keep before summarizing.
# Larger divisor = fewer events kept = more aggressive condensing.
# Scout needs less history (exploring), writer needs more (building on context).
SCOUT_CONDENSER_DIVISOR: int = 5000
WRITER_CONDENSER_DIVISOR: int = 4000

# Maximum output tokens for planner tier.  Plans are structured JSON and
# rarely exceed 8K tokens; 16K provides margin without wasting quota.
PLANNER_OUTPUT_CAP: int = 16_384

# Maximum number of existing documents included in per-crate scout context.
# More docs = better cross-reference awareness, but consumes context window.
DOC_CONTEXT_LIMIT: int = 10

# Git diff output is truncated to this many characters to avoid flooding
# the scout's context window during regeneration runs.
GIT_DIFF_TRUNCATION: int = 10_000

# Content snippet length when summarizing existing documents for the
# diff scout.  Enough to convey structure without consuming full context.
CONTENT_SNIPPET_LENGTH: int = 2000

# Maximum files listed in a single scout assignment prompt.  Beyond this
# the prompt becomes too long and quality degrades.
FILE_ASSIGNMENT_LIMIT: int = 50

# SHA-256 hex prefix length for file-change detection.
# 16 hex chars = 64 bits, collision-safe for <100K files per repo.
FILE_HASH_LENGTH: int = 16

# Existing document content truncation for the regeneration planner.
# Longer than CONTENT_SNIPPET_LENGTH because the planner needs more context
# to decide which sections need updating.
EXISTING_SUMMARY_TRUNCATION: int = 3000


# ---------------------------------------------------------------------------
# Shared Prompt Components
# ---------------------------------------------------------------------------

PROSE_REQUIREMENTS: str = """
WRITING STYLE (ABSOLUTELY MANDATORY):

Write professional, concise technical documentation. Each page should be
SHORT — 1-2 printed pages maximum. Think wiki page, not book chapter.

Use flowing prose paragraphs of 2-4 sentences. Use transition words to
connect ideas. NEVER use bullet points or dashes for descriptions — weave
items into sentences. Code blocks and tables are acceptable but surround
them with brief explanatory prose.

If a topic is too large for 1-2 pages, split it into sub-pages and link
to them with [[wikilinks]]. Prefer many small focused pages over few
large ones.
"""

TABLE_REQUIREMENTS: str = """
GFM TABLES (use when they aid comprehension):

Use GitHub-Flavored Markdown tables for structured data: endpoint summaries,
config options, comparison matrices, dependency lists, component tables.
Every table needs a header row and separator (|---|---|).
Not every page needs a table — use them where they genuinely help.
"""

DIAGRAM_REQUIREMENTS: str = """
MERMAID DIAGRAMS (use where visual relationships matter):

Use ```mermaid code blocks. Choose the right type:
  graph TB/TD: for architecture, component relationships
  sequenceDiagram: for request flows, data pipelines
  stateDiagram-v2: for stateful entities
  erDiagram: for data models

Include a brief caption sentence. Not every page needs a diagram — use
them on architecture, flow, and data model pages where they genuinely
clarify relationships.
"""

WIKILINK_REQUIREMENTS: str = """
WIKILINKS (THIS IS THE MOST IMPORTANT REQUIREMENT):

Use [[Page Title]] syntax to build a densely interconnected knowledge graph.
Wikilinks are what make this feel like a human-crafted wiki, not AI output.

INLINE WIKILINKS — EMBEDDED NATURALLY IN PROSE (this is the primary form):
  Weave links into sentences where a reader would naturally want to drill
  deeper. Examples of GOOD inline wikilinks:
    "The [[Document Service]] validates input before delegating to the
     [[Document Repository]] for persistence."
    "Authentication is handled via JWT tokens, as described in
     [[Authentication Flow]], and configured through [[Environment Variables]]."
    "This component follows the [[Repository Pattern]], abstracting all
     database queries behind a clean interface."

  BAD wikilinks (don't do this):
    "See [[Architecture]] for more." — lazy, tells the reader nothing
    "Related: [[X]], [[Y]], [[Z]]" — dumping links without context

  The key test: would a human editor naturally hyperlink this word?
  If the reader would think "what's that?" or "tell me more", it's a link.

RULES:
  - Link significant nouns the FIRST time they appear in each section
  - Every service, component, pattern, technology, and config concept
    that has its own page should be wikilinked where it's mentioned
  - DON'T over-link: same word linked twice in one paragraph is too much
  - DON'T dump links: a list of bare [[links]] with no prose is useless

DO NOT ADD A "SEE ALSO" SECTION. EVER.
  No "## See Also", no "Related pages", no link dump at the bottom.
  Every wikilink must be INLINE in prose where it's contextually relevant.
  If a connection matters, it belongs in a sentence. If it doesn't fit
  naturally in a sentence, it's not a real connection — don't force it.
  The dependency graph must reflect genuine relationships, not padding.

EXTERNAL LINKS vs WIKILINKS:
  Use [[Page Title]] ONLY for pages that exist in this wiki (listed in the
  sibling pages section below). For external resources — frameworks, libraries,
  third-party tools, specifications — use standard markdown link syntax:
  [display text](https://url).

  Examples:
    GOOD: "The [[Document Service]] validates input before persistence."
    GOOD: "Built on [FastAPI](https://fastapi.tiangolo.com/) for the backend."
    GOOD: "Uses the [OpenHands SDK](https://docs.all-hands.dev/) for agent orchestration."
    BAD:  "Built on [[FastAPI]] for the backend." — FastAPI is not a wiki page
    BAD:  "Uses the [[OpenHands SDK]] for orchestration." — external, not a wiki page

  RULE: If the concept is NOT in the list of wiki pages provided to you,
  it MUST be a standard markdown link [text](url) with an actual URL.
  Do NOT create wikilinks for external tools, libraries, or resources.
"""


# ---------------------------------------------------------------------------
# Scout Definitions
# ---------------------------------------------------------------------------

SCOUT_DEFINITIONS: dict[str, dict[str, object]] = {
    "structure": {
        "name": "Structure & Overview",
        "always_run": True,
        "prompt": """You are a repository scout. Your mission: produce a structured intelligence report about the overall structure of the repository at {repo_path}.

{file_manifest}
{constraints}

DO THIS:
1. Read README.md (or README.rst, README.txt) if it exists
2. Read package metadata files marked with ★ above (pyproject.toml, package.json, Cargo.toml, etc.)
3. Note the directory layout from the manifest above — do NOT run `find` or `ls`

Write your report to /tmp/scout_report_structure.md with this format:

## Scout Report: Structure & Overview
### Key Findings
- Project name and description (from README/package files)
- Primary language(s) and framework(s) detected
- Total file count and source file count
- High-level directory layout (what each top-level dir contains)
- Build system / package manager used
- License

### Raw Data
- Directory tree (top 2 levels, derived from the manifest)
- Package metadata summary
- README summary (first ~500 chars)

Be thorough but concise. Facts only, no opinions.""",
    },
    "architecture": {
        "name": "Architecture & Code",
        "always_run": True,
        "prompt": """You are a repository scout. Your mission: produce a structured intelligence report about the architecture and code organization of the repository at {repo_path}.

{file_manifest}
{constraints}

DO THIS:
1. Identify entry points from the ★-marked files (main.py, app.py, index.ts, etc.)
2. Read the main entry point(s) and trace key imports
3. Identify layers: routes/controllers, services/business logic, models/data, utilities
4. Read 3-5 core source files (prefer ★-marked, check sizes before reading)
5. Check for shared types, interfaces, or base classes

Write your report to /tmp/scout_report_architecture.md with this format:

## Scout Report: Architecture & Code
### Key Findings
- Entry point(s) and how the application starts
- Module/package organization (layers, domains)
- Core abstractions: key classes, functions, interfaces
- Design patterns identified
- Dependency flow (what depends on what)
- Database / storage approach (if any)

### Raw Data
- Import graph summary (main entry → what it imports)
- Key file list with one-line descriptions
- Notable code patterns with file references

Be thorough but concise. Facts only, no opinions.""",
    },
    "api": {
        "name": "API & Interfaces",
        "always_run": True,
        "prompt": """You are a repository scout. Your mission: produce a structured intelligence report about the APIs and public interfaces of the repository at {repo_path}.

{file_manifest}
{constraints}

DO THIS:
1. Read ★-marked files — these likely contain route/endpoint/schema definitions
2. Use grep to find route definitions if needed: grep -rn "@app\\|@router\\|HandleFunc" --include="*.py" --include="*.ts" --include="*.go" . | head -30
3. Read API route files to understand endpoint signatures (check sizes first!)
4. Look for OpenAPI/Swagger specs, GraphQL schemas, or protobuf definitions
5. Check for authentication/authorization middleware

Write your report to /tmp/scout_report_api.md with this format:

## Scout Report: API & Interfaces
### Key Findings
- API style (REST, GraphQL, gRPC, CLI, library)
- Authentication mechanism (JWT, API key, OAuth, none)
- Number of endpoints/routes found
- Key request/response models
- Error handling approach

### Raw Data
- Endpoint table: Method | Path | Handler | Auth Required
- Schema/model list with field summaries

If the project has no API (e.g., it's a library or CLI tool), document the public interface instead: exported functions, classes, CLI commands.

Be thorough but concise. Facts only, no opinions.""",
    },
    "infra": {
        "name": "Infrastructure & Config",
        "always_run": False,
        "prompt": """You are a repository scout. Your mission: produce a structured intelligence report about the infrastructure and configuration of the repository at {repo_path}.

{file_manifest}
{constraints}

DO THIS:
1. Read ★-marked files — these are the infrastructure and config files
2. Read Dockerfile(s), docker-compose.yml if present
3. Read CI/CD configs (.github/workflows/, etc.)
4. Read .env.example or .env.template if present
5. Check for deployment configs (Kubernetes, Terraform, Procfile)

Write your report to /tmp/scout_report_infra.md with this format:

## Scout Report: Infrastructure & Config
### Key Findings
- Containerization approach (Docker details)
- CI/CD pipeline description
- Environment variables required
- Deployment strategy
- External service dependencies

### Raw Data
- Dockerfile summary (base image, stages, exposed ports)
- docker-compose services table: Service | Image | Ports | Dependencies
- CI/CD pipeline steps
- Environment variable table: Variable | Purpose | Required | Default

Be thorough but concise. Facts only, no opinions.""",
    },
    "tests": {
        "name": "Tests & Quality",
        "always_run": False,
        "prompt": """You are a repository scout. Your mission: produce a structured intelligence report about the testing and quality setup of the repository at {repo_path}.

{file_manifest}
{constraints}

DO THIS:
1. Review ★-marked files — these are test files and test configs
2. Read 2-3 test files to understand patterns (check sizes first!)
3. Look for test configuration in the manifest: pytest.ini, jest.config.*, conftest.py
4. Check for linting/formatting configs: .eslintrc, ruff.toml, pyproject.toml [tool.ruff]

Write your report to /tmp/scout_report_tests.md with this format:

## Scout Report: Tests & Quality
### Key Findings
- Test framework(s) used
- Test file count and organization
- Testing patterns (unit, integration, e2e)
- Code quality tools (linters, formatters, type checkers)
- Coverage configuration (if any)

### Raw Data
- Test directory structure (from manifest)
- Sample test patterns (describe how tests are structured)
- Quality tool configuration summary

Be thorough but concise. Facts only, no opinions.""",
    },
}


# ---------------------------------------------------------------------------
# Scout Focus Patterns
# Per-scout focus: files matching these substrings get highlighted with ★
# ---------------------------------------------------------------------------

SCOUT_FOCUS: dict[str, dict[str, object]] = {
    "structure": {
        "patterns": ["README", "pyproject.toml", "package.json", "Cargo.toml",
                     "go.mod", "pom.xml", "Gemfile", "setup.py", "setup.cfg",
                     "LICENSE", "CHANGELOG"],
        "description": "metadata files (README, package manifests, license)",
    },
    "architecture": {
        "patterns": ["main.", "app.", "index.", "__init__.", "mod.rs",
                     "src/", "lib/", "app/", "pkg/", "internal/", "cmd/"],
        "description": "entry points and main source directories",
    },
    "api": {
        "patterns": ["route", "endpoint", "controller", "handler", "api",
                     "view", "schema", "dto", "serializer", "openapi",
                     "swagger", "graphql", "proto"],
        "description": "API routes, schemas, and interface definitions",
    },
    "infra": {
        "patterns": ["Dockerfile", "docker-compose", ".github/", "Makefile",
                     "Jenkinsfile", ".gitlab-ci", ".circleci", "Procfile",
                     "terraform", "serverless", ".env"],
        "description": "infrastructure, CI/CD, and deployment configs",
    },
    "tests": {
        "patterns": ["test", "spec", "conftest", "jest.config", "pytest",
                     "vitest", ".mocharc", "cypress"],
        "description": "test files and testing configuration",
    },
}


# ---------------------------------------------------------------------------
# Repo Analysis Patterns
# ---------------------------------------------------------------------------

# Regex patterns for lightweight import detection (no tree-sitter needed)
IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
    ".py": [
        re.compile(r"^\s*from\s+([\w.]+)\s+import"),
        re.compile(r"^\s*import\s+([\w.]+)"),
    ],
    ".ts": [
        re.compile(r"""from\s+['"]([^'"]+)['"]"""),
        re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    ],
    ".tsx": [
        re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    ],
    ".js": [
        re.compile(r"""from\s+['"]([^'"]+)['"]"""),
        re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    ],
    ".jsx": [
        re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    ],
    ".go": [
        re.compile(r'^\s*"([^"]+)"'),
    ],
    ".rs": [
        re.compile(r"^\s*use\s+([\w:]+)"),
        re.compile(r"^\s*mod\s+(\w+)"),
    ],
}

# Entry-point file patterns for module detection
ENTRY_POINT_PATTERNS: set[str] = {"main.", "app.", "index.", "__init__.py", "mod.rs", "lib.rs"}
