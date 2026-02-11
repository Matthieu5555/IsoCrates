'use client';

import React, { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, FileText, Folder, RefreshCw } from 'lucide-react';
import { deleteDocument, createDocument, createFolderMetadata, deleteFolder, type CreateDocumentData } from '@/lib/api/documents';
import { getApiErrorMessage } from '@/lib/api/client';
import type { TreeNode } from '@/types';
import { ContextMenu } from './ContextMenu';
import { TreeNodeRow } from './TreeNodeRow';
import { NewDocumentDialog } from './dialogs/NewDocumentDialog';
import { NewFolderDialog } from './dialogs/NewFolderDialog';
import { ConfirmDialog } from './dialogs/ConfirmDialog';
import { DeleteFolderDialog } from './dialogs/DeleteFolderDialog';
import { FolderPickerDialog } from './dialogs/FolderPickerDialog';
import { BulkActionBar } from './BulkActionBar';
import { executeBatch } from '@/lib/api/documents';
import { buttonVariants, overlayVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';
import { useUIStore } from '@/lib/store/uiStore';
import { useTreeData } from '@/hooks/useTreeData';
import { useTreeDragDrop } from '@/hooks/useTreeDragDrop';
import { useTreeSelection } from '@/hooks/useTreeSelection';
import { useTreeDialogs } from '@/hooks/useTreeDialogs';

export function DocumentTree() {
  const router = useRouter();

  // --- Extracted hooks ---
  const {
    tree,
    loading,
    error,
    expandedNodes,
    generationStatus,
    loadTree,
    toggleNode,
    setExpandedNodes,
    removeNode,
  } = useTreeData();

  const {
    draggedNode,
    dropTargetId,
    rootDropActive,
    movingFolder,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
    handleRootDragOver,
    handleRootDragLeave,
    handleRootDrop,
  } = useTreeDragDrop({ onTreeChanged: loadTree, setExpandedNodes });

  const {
    selectedIds,
    setSelectedIds,
    handleSelect,
    clearSelection,
  } = useTreeSelection();

  // --- Dialog/context-menu state (extracted hook) ---
  const {
    contextMenu,
    setContextMenu,
    newDocDialogOpen,
    setNewDocDialogOpen,
    newFolderDialogOpen,
    setNewFolderDialogOpen,
    deleteConfirmOpen,
    setDeleteConfirmOpen,
    deleteFolderDialogOpen,
    setDeleteFolderDialogOpen,
    selectedNode,
    setSelectedNode,
    defaultPath,
    folderPickerOpen,
    setFolderPickerOpen,
    handleDeleteClick,
    handleNewDocClick,
    handleNewFolderClick,
    closeContextMenu,
  } = useTreeDialogs();

  // --- Event handlers (stable refs for memoized TreeNodeRow) ---

  const handleNodeClick = useCallback((node: TreeNode, e?: React.MouseEvent) => {
    const result = handleSelect(node, e);
    if (result === 'selected') return;

    if (node.type === 'document') {
      router.push(`/docs/${node.id}`);
    } else {
      toggleNode(node.id);
    }
  }, [handleSelect, router, toggleNode]);

  const handleContextMenu = useCallback((e: React.MouseEvent, node: TreeNode) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }, []);

  function countDocumentsInTree(node: TreeNode): number {
    if (node.type === 'document') return 1;
    let count = 0;
    if (node.children) {
      for (const child of node.children) count += countDocumentsInTree(child);
    }
    return count;
  }

  async function handleDeleteFolderConfirm(action: 'move_up' | 'delete_all') {
    if (!selectedNode || selectedNode.type !== 'folder') return;
    try {
      const folderPath = selectedNode.path || '';
      const result = await deleteFolder(folderPath, action);
      if (action === 'move_up') {
        toast.success('Folder deleted', `${result.affected_documents} document(s) moved to parent`);
      } else {
        toast.success('Folder deleted', `${result.affected_documents} document(s) removed`);
      }
      await loadTree();
      setDeleteFolderDialogOpen(false);
      setSelectedNode(null);
    } catch (err) {
      toast.error('Delete failed', getApiErrorMessage(err));
    }
  }

  async function handleDeleteConfirm() {
    if (!selectedNode) return;
    try {
      if (selectedNode.type === 'document') {
        await deleteDocument(selectedNode.id);
        // Server-first removal: update local tree after successful API delete
        // instead of full refetch for responsiveness.
        removeNode(selectedNode.id);
        useUIStore.getState().setTrashCount(useUIStore.getState().trashCount + 1);
        toast.success('Moved to trash', 'Document can be restored from the Trash');
      }
      setDeleteConfirmOpen(false);
      setSelectedNode(null);
    } catch (err) {
      toast.error('Delete failed', getApiErrorMessage(err));
    }
  }

  async function handleCreateDocument(data: {
    title: string; path: string; content: string;
  }) {
    try {
      const createData: CreateDocumentData = {
        path: data.path,
        title: data.title,
        content: data.content,
        author_type: 'human',
      };
      const newDoc = await createDocument(createData);
      setNewDocDialogOpen(false);
      await loadTree();
      router.push(`/docs/${newDoc.id}`);
      toast.success('Document created', `Created: ${data.title}`);
    } catch (err) {
      toast.error('Create failed', getApiErrorMessage(err));
    }
  }

  async function handleCreateFolder(folderData: { path: string; description?: string }) {
    try {
      await createFolderMetadata({
        path: folderData.path,
        description: folderData.description,
      });
      setNewFolderDialogOpen(false);
      await loadTree();
      toast.success('Folder created', `Created folder: ${folderData.path}`);
    } catch (err) {
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes('already exists') || msg.includes('duplicate')) {
          toast.error('Folder already exists', `"${folderData.path}" already exists`);
        } else {
          toast.error('Create failed', err.message);
        }
      } else {
        toast.error('Create failed', 'An unexpected error occurred');
      }
    }
  }

  if (loading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading...</div>;
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="text-sm text-muted-foreground mb-2">Could not load documents</div>
        <button onClick={loadTree} className="text-sm text-primary hover:underline">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col relative">
      {movingFolder && (
        <div className={overlayVariants.loading}>
          <div className="bg-background border border-border p-4 rounded-lg shadow-lg">
            Moving...
          </div>
        </div>
      )}

      <div className="p-3 border-b border-border flex items-center gap-2">
        <button
          onClick={() => handleNewDocClick()}
          className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs`}
          title="New Document"
        >
          <Plus className="h-3 w-3" />
          <FileText className="h-3 w-3" />
        </button>
        <button
          onClick={() => handleNewFolderClick()}
          className={`${buttonVariants.iconSmall} flex items-center gap-1 text-xs`}
          title="New Folder"
        >
          <Plus className="h-3 w-3" />
          <Folder className="h-3 w-3" />
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

      {/* Tree container with root-level drop zone */}
      <div
        className={`flex-1 overflow-y-auto p-4 space-y-1 ${
          rootDropActive ? 'ring-2 ring-primary/50 ring-inset bg-primary/5' : ''
        }`}
        onDragOver={handleRootDragOver}
        onDragLeave={handleRootDragLeave}
        onDrop={handleRootDrop}
      >
        {tree.map(node => (
          <TreeNodeRow
            key={node.id}
            node={node}
            level={0}
            expandedNodes={expandedNodes}
            dropTargetId={dropTargetId}
            selectedIds={selectedIds}
            generationStatus={generationStatus}
            onNodeClick={handleNodeClick}
            onContextMenu={handleContextMenu}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onDragEnd={handleDragEnd}
          />
        ))}

        {/* Visual hint for root drop */}
        {draggedNode && (
          <div className={`mt-2 border-2 border-dashed rounded-lg p-3 text-center text-xs text-muted-foreground transition-colors ${
            rootDropActive ? 'border-primary text-primary' : 'border-border'
          }`}>
            Drop here to move to root level
          </div>
        )}
      </div>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          nodeType={contextMenu.node.type}
          onClose={closeContextMenu}
          onDelete={() => handleDeleteClick(contextMenu.node)}
          onNewDocument={() => {
            const path = contextMenu.node.path || '';
            handleNewDocClick(path);
          }}
          onNewFolder={() => {
            const path = contextMenu.node.path || '';
            handleNewFolderClick(path);
          }}
        />
      )}

      <NewDocumentDialog
        open={newDocDialogOpen}
        onClose={() => setNewDocDialogOpen(false)}
        onSubmit={handleCreateDocument}
        defaultPath={defaultPath}
      />

      <NewFolderDialog
        open={newFolderDialogOpen}
        onClose={() => setNewFolderDialogOpen(false)}
        onSubmit={handleCreateFolder}
        defaultPath={defaultPath}
      />

      <ConfirmDialog
        open={deleteConfirmOpen}
        onClose={() => {
          setDeleteConfirmOpen(false);
          setSelectedNode(null);
        }}
        onConfirm={handleDeleteConfirm}
        title="Move to trash?"
        message={`Move "${selectedNode?.name}" to trash? You can restore it later.`}
        confirmText="Move to Trash"
        variant="danger"
      />

      <DeleteFolderDialog
        open={deleteFolderDialogOpen}
        onClose={() => {
          setDeleteFolderDialogOpen(false);
          setSelectedNode(null);
        }}
        onConfirm={handleDeleteFolderConfirm}
        folder={selectedNode}
        documentCount={selectedNode ? countDocumentsInTree(selectedNode) : 0}
      />

      <BulkActionBar
        selectedIds={selectedIds}
        onClearSelection={clearSelection}
        onComplete={loadTree}
        onPickFolder={() => setFolderPickerOpen(true)}
      />

      <FolderPickerDialog
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
        tree={tree}
        onSelect={async (targetPath) => {
          setFolderPickerOpen(false);
          try {
            const result = await executeBatch('move', Array.from(selectedIds), { target_path: targetPath });
            toast.success('Moved', `${result.succeeded} document(s) moved`);
            if (result.failed > 0) {
              toast.warning('Partial failure', `${result.failed} document(s) failed`);
            }
            clearSelection();
            await loadTree();
          } catch {
            toast.error('Batch move failed', 'An unexpected error occurred');
          }
        }}
      />
    </div>
  );
}
