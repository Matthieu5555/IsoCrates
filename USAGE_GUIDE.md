# IsoCrates - User Guide

## Quick Reference

This guide covers the features of IsoCrates' folder and document management system.

## Creating Folders

### How to Create a Folder

1. Click the "+ Folder" button in the toolbar, OR
2. Right-click a folder → "New Folder"
3. Fill in the dialog:
   - **Path:** Full path for the folder (e.g., `backend/guides/advanced`)
   - **Description (optional):** Brief description of the folder's purpose
4. Click "Create Folder"

The folder will appear immediately in the tree, even without any documents.

**Example:**
```
Path: backend/guides
Description: Backend development guides and tutorials
```

## Creating Documents

### How to Create a Document

1. Click the "+ Document" button
2. Fill in the form:
   - **Path:** Where the document lives (e.g., `backend/guides/getting-started`)
   - **Title:** Document title
   - **Content:** Document content in Markdown
3. Click "Create Document"

**Example:**
```
Path: backend/guides/getting-started
Title: Installation Guide
Content: # Installation Guide...
```

## Moving Folders

Folders can be moved anywhere in the tree via drag-and-drop.

### How to Move a Folder

1. **Drag the folder** to the target folder
2. All documents inside the folder will be updated with new paths
3. A toast notification confirms the move

**Example:**
```
Dragging: "backend/api-docs" → "frontend" folder
Result: All documents move to "frontend/api-docs"
Affected: 15 documents
```

## Deleting Folders

### How to Delete a Folder

1. **Right-click the folder** → "Delete"
2. The **Delete Folder Dialog** appears with two options:

#### Option 1: Move contents up (Recommended)
- Deletes the folder
- **Keeps all documents**
- Documents move to the parent folder

#### Option 2: Delete everything
- Deletes the folder
- **Deletes all documents inside**
- Shows red warning: "This cannot be undone"

3. Select your option and click confirm

**Example:**
```
Folder: backend/guides
Contains: 10 documents

Option 1 (Move up):
  Documents moved to "backend/" (parent)

Option 2 (Delete all):
  10 documents permanently deleted
```

## Visual Hierarchy Guide

Documents are organized in a 2-level hierarchy:

```
Folder (top-level = "crate")    → Top-level category with crate icon
  └─ Folder                     → Nested folders
     └─ Document                → Individual markdown files
```

Top-level folders are called "crates" and display a special icon, but they are just folders.

### Icon Legend

> **Note:** Emoji shown here are representations. The actual UI uses Lucide React icons.

| Icon | Lucide Icon | Type | Color | Meaning |
|------|-------------|------|-------|---------|
| Layers | Layers | Crate (top-level folder) | Blue | Top-level category (backend, frontend) |
| Folder | Folder | Folder (closed) | Amber | Folder with contents |
| FolderOpen | FolderOpen | Folder (open) | Amber | Expanded folder |
| FileText | FileText | Document | Gray | Individual document |

### Badges

- **Number badge** (e.g., `5`) - Document count in folder
- **"empty" badge** - Folder has no contents
- **Client/Server badges** - doc_type indicators

### Tooltips

Hover over any node to see:
- Folder description (if set)
- Full path
- Document count

**Example Tooltip:**
```
Backend development guides • Path: backend/guides • 12 document(s)
```

## Folder Descriptions

You can add descriptions to folders that appear in the tree.

### How to Add/Edit Folder Description

1. Create folder with description (during creation), OR
2. Use the API to update folder metadata:

```bash
curl -X PUT http://localhost:8000/api/folders/metadata/{folder_id} \
  -H "Content-Type: application/json" \
  -d '{"description": "API documentation and examples"}'
```

Descriptions appear as small italic text below the folder name.

## Tips & Best Practices

### Organizing Content

**Crates (top-level folders, Layers icon)**
- Use for top-level categories: `backend`, `frontend`, `docs`, `guides`
- Keep names short and clear

**Folders (Folder icon)**
- Use for logical grouping: `api`, `tutorials`, `advanced`
- Can be nested arbitrarily deep
- Add descriptions for clarity

**Documents (FileText icon)**
- Use descriptive titles
- Keep in appropriate folders
- Use wikilinks `[[Other Doc]]` for cross-references

### Folder Organization Strategies

**By Feature:**
```
backend/
  ├── authentication/
  ├── api/
  ├── database/
  └── testing/
```

**By Audience:**
```
docs/
  ├── developers/
  ├── users/
  └── administrators/
```

**By Type:**
```
guides/
  ├── tutorials/
  ├── how-to/
  ├── reference/
  └── troubleshooting/
```

## Personal Tree

The Personal Tree lets you create your own organization of documents without affecting the shared Org Tree. You create folders and add **references** to org documents — not copies. The org document stays in one place; your personal tree is just your own lens into it.

### Switching Trees

At the bottom of the sidebar, two tabs let you switch between:
- **Org Tree** — The shared organizational tree (default)
- **Personal Tree** — Your personal organization

Your tab preference is persisted across sessions.

### Creating Personal Folders

1. Switch to the **Personal Tree** tab
2. Click the "+ Folder" button in the toolbar, OR right-click a folder → "New Subfolder"
3. Enter a folder name (no paths — just a name like `My APIs`)
4. Click "Create Folder"

Personal folders can be nested. They are independent of the org tree structure.

### Adding Documents to Your Personal Tree

1. Click the "+ Link" button in the toolbar, OR right-click a folder → "Add Document"
2. A search dialog appears — type to find org documents
3. Click "Add" next to any document to reference it in the selected folder

The document is **not copied** — it's a reference. If the org document is updated, your personal tree always shows the latest version. If the org document is deleted, the reference is automatically removed.

### Removing References

Right-click a document in your personal tree → "Remove Reference". This only removes it from your personal tree — the org document is not affected.

### Deleting Personal Folders

Right-click a folder → "Delete Folder". This deletes the folder and all references inside it. Org documents are never affected.

### Icon Legend (Personal Tree)

| Icon | Meaning |
|------|---------|
| Folder / FolderOpen | Personal folder |
| FileText + Link | Document reference (linked from org) |

### API Usage

```bash
# Get personal tree
curl http://localhost:8000/api/personal/tree?user_id=default

# Create personal folder
curl -X POST http://localhost:8000/api/personal/folders \
  -H "Content-Type: application/json" \
  -d '{"name": "My Notes", "parent_id": null}'

# Add document reference to folder
curl -X POST http://localhost:8000/api/personal/folders/{folder_id}/refs \
  -H "Content-Type: application/json" \
  -d '{"document_id": "doc-abc123"}'

# Remove reference
curl -X DELETE http://localhost:8000/api/personal/refs/{ref_id}

# Delete personal folder
curl -X DELETE http://localhost:8000/api/personal/folders/{folder_id}
```

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Search | CMD+K / Ctrl+K |
| New Document | Click "+ Doc" button |
| New Folder | Click "+ Folder" button |
| Delete | Right-click → Delete |
| Refresh Tree | Click refresh button |
| Expand/Collapse | Click folder name |

## Common Workflows

### Creating a Documentation Hierarchy

1. Create top-level folder (crate): `docs`
2. Create sub-folders:
   - `docs/getting-started`
   - `docs/advanced`
   - `docs/api-reference`
3. Add documents to each folder
4. Add folder descriptions for clarity

### Reorganizing Content

**Move folder:**
- Drag and drop to target folder

**Consolidate folders:**
1. Delete old folder with "Move contents up"
2. Documents move to parent
3. Manually organize if needed

### Cleaning Up Empty Folders

**Keep empty folder:**
- Leave it as-is (it has metadata and shows "empty" badge)

**Remove empty folder:**
- Right-click → Delete
- Choose either option (no contents to worry about)

## Troubleshooting

### Folder doesn't appear in tree
**Cause:** Folder metadata not created
**Solution:** Create folder using "+ Folder" button or API

### Wikilinks broken after moving folder
**Cause:** Wikilinks use old paths
**Solution:** Manually update wikilinks

### Empty folder disappeared after deleting last document
**Cause:** No folder metadata was created
**Solution:** Recreate folder with "+ Folder" button (creates metadata)

## API Usage Examples

### Create Empty Folder

```bash
curl -X POST http://localhost:8000/api/folders/metadata \
  -H "Content-Type: application/json" \
  -d '{
    "path": "backend/guides/advanced",
    "description": "Advanced backend development topics"
  }'
```

### Create Document

```bash
curl -X POST http://localhost:8000/api/docs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "backend/guides/getting-started",
    "title": "Quick Start",
    "content": "# Quick Start Guide\n\nWelcome to...",
    "author_type": "human"
  }'
```

### Move Folder

```bash
curl -X PUT http://localhost:8000/api/folders/move \
  -H "Content-Type: application/json" \
  -d '{
    "source_path": "backend/api/auth",
    "target_path": "frontend/api/auth"
  }'
```

### Delete Folder (Move Contents Up)

```bash
curl -X DELETE "http://localhost:8000/api/folders/backend/api?action=move_up"
```

### Delete Folder (Delete All Contents)

```bash
curl -X DELETE "http://localhost:8000/api/folders/backend/api?action=delete_all"
```

## Authentication

When `AUTH_ENABLED=true` (production), write operations (create, update, delete) require a JWT bearer token. Read operations work without authentication.

```bash
# Generate a token (using the backend's token factory)
TOKEN=$(python -c "from app.core.token_factory import create_token; print(create_token('user', 'admin', 'your-jwt-secret'))")

# Use it in requests
curl -X POST http://localhost:8000/api/docs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"path": "test", "title": "Hello", "content": "# Hello"}'
```

In development (`AUTH_ENABLED=false`, the default), no token is needed.

## Getting Help

- See [ARCHITECTURE.md](ARCHITECTURE.md) for system design and coding standards
- See [docs/DEPLOYING_AT_YOUR_ORGANIZATION.md](docs/DEPLOYING_AT_YOUR_ORGANIZATION.md) for setup, deployment, and configuration
- See `backend/migrations/README.md` for migration info
