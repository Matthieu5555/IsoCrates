# Prompt Engineering Guide

IsoCrates generates documentation through a three-tier agent pipeline. This guide explains where each prompt lives, what it controls, and how to modify the output without breaking the pipeline's contracts.

## How the pipeline works

Think of the pipeline as a newsroom. First, scout agents (Tier 0) act as field reporters: they explore the target repository in parallel, each producing a structured intelligence report about one aspect of the codebase (structure, architecture, APIs, infrastructure, or test setup). Second, the planner (Tier 1) acts as the editor-in-chief: it reads all scout reports in a single reasoning call (no tools) and designs a documentation blueprint, a JSON object specifying what pages to write, their sections, cross-references, and folder structure. Third, writer agents (Tier 2) are the staff writers: each receives a focused brief derived from the blueprint, explores the repository to verify facts, and produces one markdown wiki page.

Every prompt the pipeline uses lives in one of two files. Static prompt fragments (the reusable building blocks injected into every writer brief) live in `agent/prompts.py`. Dynamic prompt construction (the planner's full prompt and the writer brief template) lives in `agent/planner.py` and `agent/openhands_doc.py` respectively.

## Where each prompt lives

| Prompt | File | What It Controls |
|--------|------|-----------------|
| `PROSE_REQUIREMENTS` | `agent/prompts.py` | Writing style rules, bullet point ban, page length limits |
| `TABLE_REQUIREMENTS` | `agent/prompts.py` | When and how to use GFM tables |
| `DIAGRAM_REQUIREMENTS` | `agent/prompts.py` | Mermaid diagram guidance and type selection |
| `WIKILINK_REQUIREMENTS` | `agent/prompts.py` | Wikilink density, inline linking rules, external link handling |
| `DESCRIPTION_REQUIREMENTS` | `agent/prompts.py` | Writer-authored page descriptions in bottomatter |
| `SELF_CONTAINED_REQUIREMENTS` | `agent/prompts.py` | Standalone page requirement, no assumed reading order |
| `SCOUT_DEFINITIONS` | `agent/prompts.py` | Per-scout mission prompts (what each scout explores) |
| `SCOUT_FOCUS` | `agent/prompts.py` | File patterns each scout prioritizes |
| Planner prompt | `agent/planner.py` (`DocumentPlanner.plan()`) | Full planner reasoning prompt, JSON output schema, mandatory pages, page count guidelines |
| Writer brief | `agent/openhands_doc.py` (`_build_writer_brief()`) | The brief assembled for each writer agent, combining all `*_REQUIREMENTS` constants with document-specific context |

## Common customizations

### Changing writing style

All writing style rules are defined as string constants in `agent/prompts.py`. The `PROSE_REQUIREMENTS` constant controls the core style mandate: flowing prose, the bullet point ban, and page length guidance. To adjust the tone (say, from technical to conversational), edit this constant directly. The writer brief in `agent/openhands_doc.py` injects it via `{PROSE_REQUIREMENTS}`, so changes propagate to every writer automatically.

The same pattern applies to `TABLE_REQUIREMENTS`, `DIAGRAM_REQUIREMENTS`, and the other `*_REQUIREMENTS` constants. Each is a self-contained block of instructions that the writer brief interpolates. You can edit any of them independently without affecting the others.

### Adding a new prompt block

Follow the existing pattern. Define a new string constant in `agent/prompts.py`, then import it in `agent/openhands_doc.py` and add `{YOUR_NEW_CONSTANT}` to the writer brief inside `_build_writer_brief()`. The brief is a single f-string, so inserting a new block is a one-line change. Keep each block focused on one concern, because that modularity is what makes these prompts maintainable.

### Changing mandatory pages

The planner prompt in `agent/planner.py` includes a `MANDATORY PAGES` section (inside `DocumentPlanner.plan()`) that lists the pages every documentation set must include. Currently these are Overview, Getting Started, and Capabilities and User Stories. To add or remove mandatory pages, edit that section of the planner prompt. The planner's JSON output schema (also in the same prompt) shows the expected structure for each document entry.

### Adjusting page count and complexity thresholds

The planner prompt contains `PAGE COUNT GUIDELINES` that map repository size to recommended page counts (small repos get 5 to 8 pages, medium get 8 to 15, large get 15 to 25). These are guidelines the planner follows when deciding how many pages to generate. Adjust the numbers to suit your organization's documentation density preferences.

### Modifying scout behavior

Each scout's mission is defined in `SCOUT_DEFINITIONS` in `agent/prompts.py`. The dictionary maps scout keys (like `"structure"`, `"architecture"`, `"api"`) to their prompts. The `always_run` flag determines whether a scout runs for every repository or only when the repository is complex enough. The `SCOUT_FOCUS` dictionary controls which files get highlighted with a star marker in each scout's file manifest, directing their attention to the most relevant files.

To add a new scout, add an entry to both `SCOUT_DEFINITIONS` and `SCOUT_FOCUS`. The scout runner in `agent/scout.py` iterates over these dictionaries automatically.

### Modifying description behavior

Writers are instructed to include a page description in the bottomatter block (the `---` delimited metadata at the end of the file). The pipeline extracts this description and sends it to the backend, falling back to the planner's pre-content description if the writer omits one. The `DESCRIPTION_REQUIREMENTS` constant in `agent/prompts.py` controls the instructions writers receive about this. The extraction logic lives in `agent/openhands_doc.py` in `generate_document()`, where `parse_bottomatter()` returns the metadata dictionary.

## Preserving the JSON contract

The planner outputs a JSON object that the rest of the pipeline parses. The expected schema is defined inline in the planner prompt (in `agent/planner.py`). If you modify the planner prompt, make sure the JSON schema section remains valid and that the `documents` array entries still include `doc_type`, `title`, `path`, `description`, `sections`, `key_files_to_read`, and `wikilinks_out`. The writer brief construction in `_build_writer_brief()` reads these fields, and the `generate_document()` method depends on them for output path computation, API payload assembly, and wikilink sanitization.

The planner also supports a `replaces_title` field on document entries, used during regeneration to tell the pipeline that a page is being renamed. Removing this field will break the title-based ID resolution logic in `generate_document()`.

## Testing changes

All agent tests use mocked LLM calls, so they cost nothing to run and complete in seconds:

```bash
cd agent && uv run pytest tests/ -v
```

The test suite in `agent/tests/test_pipeline.py` covers writer brief construction, file finding, content cleaning, API payload structure, and the description fallback chain. After modifying any prompt, run the tests to verify that the pipeline's structural contracts are intact. The tests do not validate prose quality (that requires human review), but they catch broken imports, missing fields, and logic regressions.

For a broader check across the full stack:

```bash
cd backend && uv run pytest
cd frontend && npm test
```
