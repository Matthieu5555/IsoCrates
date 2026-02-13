# IsoCrates User Guide

## Quick Reference

This guide covers everything you need to use IsoCrates: creating folders and documents, reorganizing your tree with drag-and-drop, setting up a personal tree, calling the API, and authenticating. Think of IsoCrates as a filing cabinet where folders hold your Markdown documents, and you can rearrange drawers and files whenever you want.

## Creating Folders

To create a folder, click the "+ Folder" button in the toolbar, or right-click an existing folder and choose "New Folder". The dialog asks for a full path (such as `backend/guides/advanced`) and an optional description that briefly explains the folder's purpose. Once you click "Create Folder", the new folder appears immediately in the tree, even before any documents are added to it.

```
Path: backend/guides
Description: Backend development guides and tutorials
```

## Creating Documents

To create a new document, click the "+ Document" button to open the creation form. You need to provide three things: the path where the document lives (for example, `backend/guides/getting-started`), a title, and the document content written in Markdown. After filling in these fields, click "Create Document" to add it to the tree.

```
Path: backend/guides/getting-started
Title: Installation Guide
Content: # Installation Guide...
```

## Moving Folders

Folders can be moved anywhere in the tree via drag-and-drop. Simply drag a folder onto the target folder. Because IsoCrates tracks all documents by their full path, every document inside the moved folder is automatically updated with the new path prefix. A toast notification confirms the move and shows how many documents were affected.

```
Dragging: "backend/api-docs" → "frontend" folder
Result: All documents move to "frontend/api-docs"
Affected: 15 documents
```

## Deleting Folders

Right-click the folder you want to remove and select "Delete". This opens a dialog that presents two options.

The first option, "Move contents up", is the recommended approach. It deletes the folder itself but keeps all documents intact by moving them into the parent folder. Think of it like removing a drawer divider: the files stay, they just live one level higher now. This means you can safely collapse unnecessary hierarchy levels without losing any content.

The second option, "Delete everything", removes the folder along with every document inside it. Because this action cannot be undone, the dialog displays a red warning to make sure you understand the consequences.

After selecting your preferred option, click confirm to proceed.

```
Folder: backend/guides
Contains: 10 documents

Option 1 (Move up):
  Documents moved to "backend/" (parent)

Option 2 (Delete all):
  10 documents permanently deleted
```

## Visual Hierarchy Guide

Documents are organized in a two-level hierarchy. Top-level folders are called "crates" and display a special icon, but they are functionally identical to any other folder. The distinction is purely visual, helping users immediately identify the broadest categories in their tree. Below crates sit regular folders, and inside those folders live individual Markdown documents.

```
Folder (top-level = "crate")    → Top-level category with crate icon
  └─ Folder                     → Nested folders
     └─ Document                → Individual markdown files
```

### Icon Legend

The actual UI uses Lucide React icons. The table below maps each icon to its meaning.

| Icon | Lucide Icon | Type | Color | Meaning |
|------|-------------|------|-------|---------|
| Layers | Layers | Crate (top-level folder) | Blue | Top-level category (backend, frontend) |
| Folder | Folder | Folder (closed) | Amber | Folder with contents |
| FolderOpen | FolderOpen | Folder (open) | Amber | Expanded folder |
| FileText | FileText | Document | Gray | Individual document |

### Badges and Tooltips

Folders and documents display contextual badges to convey status at a glance. A number badge (such as `5`) indicates how many documents the folder contains, while an "empty" badge signals that the folder has no contents yet. Documents may also carry Client or Server badges, which serve as doc_type indicators.

Hovering over any node reveals additional detail: the folder description (if one has been set), the full path, and the document count. Together, these tooltips let you orient yourself in the tree without opening each item.

```
Backend development guides • Path: backend/guides • 12 document(s)
```

## Folder Descriptions

You can add descriptions to folders that appear as small italic text below the folder name in the tree. Descriptions can be set at creation time by filling in the description field in the folder creation dialog. If you need to update a description after the fact, you can do so through the API:

```bash
curl -X PUT http://localhost:8000/api/folders/metadata/{folder_id} \
  -H "Content-Type: application/json" \
  -d '{"description": "API documentation and examples"}'
```

## Tips and Best Practices

### Organizing Content

Crates (top-level folders, shown with the Layers icon) work best as broad categories such as `backend`, `frontend`, `docs`, or `guides`. Because they are the first things users see, keep their names short and self-explanatory.

Folders (shown with the Folder icon) are ideal for logical grouping within those crates, like `api`, `tutorials`, or `advanced`. Since folders can be nested arbitrarily deep, you have full flexibility to create whatever hierarchy makes sense for your content. Adding descriptions to folders further improves navigability.

Documents (shown with the FileText icon) should have descriptive titles and live in the most appropriate folder. To cross-reference documents, use wikilinks with the `[[Other Doc]]` syntax, which creates navigable links between related pages.

### Folder Organization Strategies

There are several effective strategies for organizing your tree.

Organizing by feature groups content around specific system capabilities:

```
backend/
  ├── authentication/
  ├── api/
  ├── database/
  └── testing/
```

Organizing by audience makes sense when different readers need different materials:

```
docs/
  ├── developers/
  ├── users/
  └── administrators/
```

Organizing by content type works well when you produce several distinct forms of documentation:

```
guides/
  ├── tutorials/
  ├── how-to/
  ├── reference/
  └── troubleshooting/
```

## Personal Tree

The Personal Tree lets you create your own organization of documents without affecting the shared Org Tree. Think of it like creating bookmarks or shortcuts on your desktop: the actual files live in the shared tree, and your personal tree just points to them. You create folders and add references to org documents, not copies. The org document stays in one place; your personal tree is simply your own lens into it.

### Switching Trees

At the bottom of the sidebar, two tabs let you switch between the Org Tree (the shared organizational tree, shown by default) and the Personal Tree (your personal organization). Your tab preference is persisted across sessions, so the view you last selected will still be active when you return.

### Creating Personal Folders

To create a personal folder, first switch to the Personal Tree tab. Then click the "+ Folder" button in the toolbar, or right-click an existing personal folder and choose "New Subfolder". Unlike org folders, personal folders use simple names rather than full paths, so just enter something like `My APIs`. After clicking "Create Folder", the new folder appears in your personal tree. Personal folders can be nested and are entirely independent of the org tree structure, so you can arrange them however you like.

### Adding Documents to Your Personal Tree

To add a document reference, click the "+ Link" button in the toolbar or right-click a personal folder and choose "Add Document". A search dialog appears where you can type to find org documents, and clicking "Add" next to any result places a reference in the selected folder.

The document is not copied; it is a reference. If the org document is updated, your personal tree always shows the latest version. Conversely, if the org document is deleted, the reference is automatically removed from your personal tree.

### Removing References

To remove a reference, right-click the document in your personal tree and select "Remove Reference". This only removes the link from your personal tree. The underlying org document is not affected in any way.

### Deleting Personal Folders

Right-clicking a personal folder and selecting "Delete Folder" removes the folder along with all references it contains. Because these are only references, org documents are never affected by this operation.

### Personal Tree Icon Legend

| Icon | Meaning |
|------|---------|
| Folder / FolderOpen | Personal folder |
| FileText + Link | Document reference (linked from org) |

### Personal Tree API Usage

All personal tree endpoints require authentication. The user is identified from the JWT token, which means you cannot access another user's personal tree. The following examples demonstrate the available operations:

```bash
# Get your personal tree
curl http://localhost:8000/api/personal/tree \
  -H "Authorization: Bearer $TOKEN"

# Create personal folder
curl -X POST http://localhost:8000/api/personal/folders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Notes", "parent_id": null}'

# Add document reference to folder
curl -X POST http://localhost:8000/api/personal/folders/{folder_id}/refs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "doc-abc123"}'

# Remove reference
curl -X DELETE http://localhost:8000/api/personal/refs/{ref_id} \
  -H "Authorization: Bearer $TOKEN"

# Delete personal folder
curl -X DELETE http://localhost:8000/api/personal/folders/{folder_id} \
  -H "Authorization: Bearer $TOKEN"
```

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Search | CMD+K / Ctrl+K |
| New Document | Click "+ Doc" button |
| New Folder | Click "+ Folder" button |
| Delete | Right-click, then Delete |
| Refresh Tree | Click refresh button |
| Expand/Collapse | Click folder name |

## Common Workflows

### Creating a Documentation Hierarchy

A typical documentation hierarchy starts with a top-level crate such as `docs`. From there, you create sub-folders to establish your structure (for instance, `docs/getting-started`, `docs/advanced`, and `docs/api-reference`). Once the folder structure is in place, you can add documents to each folder. Adding descriptions to the folders at this stage helps future readers understand the purpose of each section without having to open it.

### Reorganizing Content

To move a folder, drag and drop it onto the desired target folder. If you need to consolidate folders instead, delete the unnecessary folder using the "Move contents up" option, which shifts all its documents into the parent. From there, you can manually reorganize specific documents if further adjustments are needed.

### Cleaning Up Empty Folders

Empty folders are harmless. They retain their metadata and display an "empty" badge in the tree, so you can leave them in place if you plan to add content later. If you want to remove an empty folder, right-click it and select "Delete". Since the folder has no contents, either deletion option produces the same result.

## Troubleshooting

### Folder does not appear in tree

This typically happens because folder metadata was not created. To resolve it, create the folder using the "+ Folder" button or the folder metadata API endpoint, which ensures the tree recognizes it.

### Wikilinks broken after moving folder

When a folder is moved, document paths are updated automatically. However, wikilinks that reference documents by their old paths will break because wikilinks are not automatically rewritten. You will need to manually update any affected wikilinks to reflect the new paths.

### Empty folder disappeared after deleting last document

If a folder vanishes after its last document is removed, it means that no folder metadata was created for it. The folder existed only implicitly, inferred from document paths. To prevent this in the future, recreate the folder using the "+ Folder" button, which creates persistent metadata that keeps the folder visible even when empty.

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

When `AUTH_ENABLED=true` (production), all API requests are permission-filtered. Users only see documents within their granted path prefixes, which means that unauthenticated users see nothing, not everything. Write operations such as create, update, and delete require a valid JWT bearer token, and read operations without a token return empty results. This design ensures that sensitive content is never exposed to unauthorized requests.

To obtain a token, log in via the authentication endpoint:

```bash
# Log in to get a token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@company.com", "password": "your-password"}' | jq -r '.token')

# Use it in requests
curl -X POST http://localhost:8000/api/docs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"path": "test", "title": "Hello", "content": "# Hello"}'
```

In development (`AUTH_ENABLED=false`, the default), no token is needed and all documents are visible.

## Getting Help

For deeper understanding of the system, consult [ARCHITECTURE.md](ARCHITECTURE.md), which covers system design and coding standards. If you need guidance on setup, deployment, or configuration, see [DEPLOYING_AT_YOUR_ORGANIZATION.md](DEPLOYING_AT_YOUR_ORGANIZATION.md). Migration-specific details are available in `backend/migrations/README.md`.
