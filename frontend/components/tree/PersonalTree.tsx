'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createPortal } from 'react-dom';
import { Plus, FileText, Folder, FolderOpen, RefreshCw, Trash2, Link2 } from 'lucide-react';
import { createPersonalFolder, deletePersonalFolder, removeDocumentRef } from '@/lib/api/personal';
import type { PersonalTreeNode } from '@/types';
import { NewFolderDialog } from './dialogs/NewFolderDialog';
import { AddDocumentDialog } from './dialogs/AddDocumentDialog';
import { ConfirmDialog } from './dialogs/ConfirmDialog';
import { buttonVariants, iconVariants, contextMenuVariants, menuItemVariants, overlayVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';
import { getApiErrorMessage } from '@/lib/api/client';
import { usePersonalTreeData } from '@/hooks/usePersonalTreeData';
import { usePersonalTreeDragDrop } from '@/hooks/usePersonalTreeDragDrop';
import { INDENT_PER_LEVEL, NODE_BASE_PADDING } from '@/lib/config/tree-constants';

export function PersonalTree() {
  const router = useRouter();

  // --- Extracted hooks ---
  const {
    tree,
    loading,
    error,
    expandedNodes,
    loadTree,
    toggleNode,
    setExpandedNodes,
  } = usePersonalTreeData();

  const {
    draggedNode,
    dropTargetId,
    rootDropActive,
    moving,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
    handleRootDragOver,
    handleRootDragLeave,
    handleRootDrop,
  } = usePersonalTreeDragDrop({ onTreeChanged: loadTree, setExpandedNodes });

  // Dialogs
  const [newFolderDialogOpen, setNewFolderDialogOpen] = useState(false);
  const [addDocDialogOpen, setAddDocDialogOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  // Context menu
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: PersonalTreeNode;
  } | null>(null);

  // Selected node for operations
  const [selectedNode, setSelectedNode] = useState<PersonalTreeNode | null>(null);
  const [selectedParentId, setSelectedParentId] = useState<string | null>(null);

  function handleNodeClick(node: PersonalTreeNode) {
    if (node.type === 'document' && node.document_id) {
      router.push(`/docs/${node.document_id}`);
    } else {
      toggleNode(node.id);
    }
  }

  function handleContextMenu(e: React.MouseEvent, node: PersonalTreeNode) {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }

  function handleNewFolderClick(parentId?: string | null) {
    setSelectedParentId(parentId ?? null);
    setNewFolderDialogOpen(true);
  }

  function handleAddDocClick(folderId?: string | null) {
    if (!folderId) {
      if (tree.length === 0) {
        toast.warning('No folders', 'Create a folder first to add documents');
        return;
      }
      folderId = tree[0].id;
    }
    setSelectedParentId(folderId);
    setAddDocDialogOpen(true);
  }

  async function handleCreateFolder(folderData: { path: string; description?: string }) {
    try {
      const name = folderData.path.split('/').pop() || folderData.path;
      await createPersonalFolder({
        name,
        parent_id: selectedParentId,
      });
      setNewFolderDialogOpen(false);
      await loadTree();
      toast.success('Folder created', `Created: ${name}`);
    } catch (err) {
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes('already exists') || msg.includes('duplicate') || msg.includes('unique')) {
          toast.error('Folder already exists', `A folder with that name already exists here`);
        } else {
          toast.error('Create failed', err.message);
        }
      } else {
        toast.error('Create failed', 'An unexpected error occurred');
      }
    }
  }

  function handleDeleteClick(node: PersonalTreeNode) {
    setSelectedNode(node);
    setDeleteConfirmOpen(true);
  }

  async function handleDeleteConfirm() {
    if (!selectedNode) return;
    try {
      if (selectedNode.type === 'folder') {
        const folderId = selectedNode.folder_id || selectedNode.id;
        await deletePersonalFolder(folderId);
        toast.success('Folder deleted');
      } else if (selectedNode.type === 'document' && selectedNode.ref_id) {
        await removeDocumentRef(selectedNode.ref_id);
        toast.success('Reference removed');
      } else {
        toast.error('Delete failed', 'Unable to determine item type');
        return;
      }
      await loadTree();
    } catch (err) {
      toast.error('Delete failed', getApiErrorMessage(err));
      throw err;
    } finally {
      setSelectedNode(null);
    }
  }

  function getSelectedFolderName(): string {
    if (!selectedParentId) return 'Root';
    function find(nodes: PersonalTreeNode[]): string | null {
      for (const n of nodes) {
        if (n.id === selectedParentId) return n.name;
        if (n.children) {
          const found = find(n.children);
          if (found) return found;
        }
      }
      return null;
    }
    return find(tree) || 'Folder';
  }

  function renderNode(node: PersonalTreeNode, level = 0) {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const indent = level * INDENT_PER_LEVEL;
    const isDropTarget = dropTargetId === node.id;

    const folderDropProps = node.type === 'folder' ? {
      onDragOver: (e: React.DragEvent) => handleDragOver(e, node),
      onDragLeave: handleDragLeave,
      onDrop: (e: React.DragEvent) => handleDrop(e, node),
    } : {};

    return (
      <div key={node.id} {...folderDropProps}>
        <div>
          <button
            onClick={() => handleNodeClick(node)}
            onContextMenu={(e) => handleContextMenu(e, node)}
            draggable={true}
            onDragStart={(e) => handleDragStart(e, node)}
            onDragOver={(e) => handleDragOver(e, node)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, node)}
            onDragEnd={handleDragEnd}
            className={`w-full text-left px-3 py-2 hover:bg-muted rounded text-sm flex items-center gap-2 transition-colors cursor-grab active:cursor-grabbing ${
              isDropTarget ? overlayVariants.dropTarget : ''
            }`}
            style={{ paddingLeft: `${indent + NODE_BASE_PADDING}px` }}
          >
            {hasChildren && (
              <span className="text-xs w-3">
                {isExpanded ? '\u25BC' : '\u25B6'}
              </span>
            )}
            {!hasChildren && <span className="w-3" />}
            {node.type === 'folder' && (
              isExpanded ? (
                <FolderOpen className={iconVariants.folder} />
              ) : (
                <Folder className={iconVariants.folder} />
              )
            )}
            {node.type === 'document' && (
              <div className="relative">
                <FileText className={iconVariants.document} />
                <Link2 className="h-2 w-2 text-primary absolute -bottom-0.5 -right-0.5" />
              </div>
            )}
            <span className="flex-1 truncate">{node.name}</span>
          </button>
        </div>
        {hasChildren && isExpanded && (
          <div>
            {node.children?.map(child => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  }

  // Close context menu on click outside
  useEffect(() => {
    if (!contextMenu) return;
    const handle = () => setContextMenu(null);
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [contextMenu]);

  if (loading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading...</div>;
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="text-sm text-muted-foreground mb-2">Could not load documents</div>
        <button onClick={loadTree} className="text-sm text-primary hover:underline">Retry</button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col relative">
      {moving && (
        <div className={overlayVariants.loading}>
          <div className="bg-background border border-border p-4 rounded-lg shadow-lg">
            Moving...
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="p-3 border-b border-border flex items-center gap-2">
        <button
          onClick={() => handleNewFolderClick(null)}
          className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs`}
          title="New Folder"
        >
          <Plus className="h-3 w-3" />
          <Folder className="h-3 w-3" />
        </button>
        <button
          onClick={() => handleAddDocClick(null)}
          className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs`}
          title="Add Document"
        >
          <Plus className="h-3 w-3" />
          <Link2 className="h-3 w-3" />
        </button>
        <div className="flex-1" />
        <button
          onClick={loadTree}
          className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs`}
          title="Refresh"
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {/* Tree with root drop zone */}
      <div
        className={`flex-1 overflow-y-auto p-4 space-y-1 ${
          rootDropActive ? 'ring-2 ring-primary/50 ring-inset bg-primary/5' : ''
        }`}
        onDragOver={handleRootDragOver}
        onDragLeave={handleRootDragLeave}
        onDrop={handleRootDrop}
      >
        {tree.length === 0 && (
          <div className="text-sm text-muted-foreground text-center py-8">
            <p className="mb-2">No personal folders yet</p>
            <p className="text-xs">Create a folder to start organizing</p>
          </div>
        )}
        {tree.map(node => renderNode(node))}

        {/* Visual hint for root drop (folders only) */}
        {draggedNode && draggedNode.type === 'folder' && (
          <div className={`mt-2 border-2 border-dashed rounded-lg p-3 text-center text-xs text-muted-foreground transition-colors ${
            rootDropActive ? 'border-primary text-primary' : 'border-border'
          }`}>
            Drop here to move to root level
          </div>
        )}
      </div>

      {/* Context menu */}
      {contextMenu && createPortal(
        <div
          className={contextMenuVariants.container}
          onMouseDown={(e) => e.stopPropagation()}
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 188),
            top: Math.min(contextMenu.y, window.innerHeight - 120),
          }}
        >
          {contextMenu.node.type === 'folder' && (
            <>
              <button
                onClick={() => {
                  handleNewFolderClick(contextMenu.node.folder_id || contextMenu.node.id);
                  setContextMenu(null);
                }}
                className={menuItemVariants.default}
              >
                <Folder className="h-4 w-4" />
                New Subfolder
              </button>
              <button
                onClick={() => {
                  handleAddDocClick(contextMenu.node.folder_id || contextMenu.node.id);
                  setContextMenu(null);
                }}
                className={menuItemVariants.default}
              >
                <Link2 className="h-4 w-4" />
                Add Document
              </button>
              <div className={contextMenuVariants.divider} />
            </>
          )}
          <button
            onClick={() => {
              handleDeleteClick(contextMenu.node);
              setContextMenu(null);
            }}
            className={menuItemVariants.danger}
          >
            <Trash2 className="h-4 w-4" />
            <span className="font-medium">
              {contextMenu.node.type === 'document' ? 'Remove Reference' : 'Delete Folder'}
            </span>
          </button>
        </div>,
        document.body
      )}

      {/* Dialogs */}
      <NewFolderDialog
        open={newFolderDialogOpen}
        onClose={() => setNewFolderDialogOpen(false)}
        onSubmit={handleCreateFolder}
        defaultPath=""
      />

      {addDocDialogOpen && selectedParentId && (
        <AddDocumentDialog
          open={addDocDialogOpen}
          onClose={() => setAddDocDialogOpen(false)}
          targetFolderId={selectedParentId}
          targetFolderName={getSelectedFolderName()}
          onAdded={() => loadTree()}
        />
      )}

      <ConfirmDialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={handleDeleteConfirm}
        title={selectedNode?.type === 'document' ? 'Remove reference?' : 'Delete folder?'}
        message={
          selectedNode?.type === 'document'
            ? `Remove "${selectedNode?.name}" from your personal tree? The org document is not affected.`
            : `Delete folder "${selectedNode?.name}" and all its contents?`
        }
        confirmText={selectedNode?.type === 'document' ? 'Remove' : 'Delete'}
        variant="danger"
      />
    </div>
  );
}
