'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, FileText, Folder, FolderOpen, Layers, RefreshCw, Clock, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { deleteDocument, createDocument, createFolderMetadata, deleteFolder, type CreateDocumentData, type CreateFolderMetadataData } from '@/lib/api/documents';
import { getApiErrorMessage } from '@/lib/api/client';
import type { TreeNode } from '@/types';
import { ContextMenu } from './ContextMenu';
import { NewDocumentDialog } from './dialogs/NewDocumentDialog';
import { NewFolderDialog } from './dialogs/NewFolderDialog';
import { ConfirmDialog } from './dialogs/ConfirmDialog';
import { DeleteFolderDialog } from './dialogs/DeleteFolderDialog';
import { FolderPickerDialog } from './dialogs/FolderPickerDialog';
import { BulkActionBar } from './BulkActionBar';
import { executeBatch } from '@/lib/api/documents';
import { buttonVariants, iconVariants, overlayVariants } from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';
import { useUIStore } from '@/lib/store/uiStore';
import { useTreeData } from '@/hooks/useTreeData';
import { useTreeDragDrop } from '@/hooks/useTreeDragDrop';
import { useTreeSelection } from '@/hooks/useTreeSelection';
import { INDENT_PER_LEVEL, NODE_BASE_PADDING } from '@/lib/config/tree-constants';

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

  // --- Local dialog/context-menu state ---
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TreeNode;
  } | null>(null);

  const [newDocDialogOpen, setNewDocDialogOpen] = useState(false);
  const [newFolderDialogOpen, setNewFolderDialogOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteFolderDialogOpen, setDeleteFolderDialogOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<TreeNode | null>(null);
  const [defaultPath, setDefaultPath] = useState('');
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

  // --- Event handlers ---

  function handleNodeClick(node: TreeNode, e?: React.MouseEvent) {
    const result = handleSelect(node, e);
    if (result === 'selected') return;

    if (node.type === 'document') {
      router.push(`/docs/${node.id}`);
    } else {
      toggleNode(node.id);
    }
  }

  function handleContextMenu(e: React.MouseEvent, node: TreeNode) {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }

  function handleDeleteClick(node: TreeNode) {
    setSelectedNode(node);
    if (node.type === 'folder') {
      setDeleteFolderDialogOpen(true);
    } else {
      setDeleteConfirmOpen(true);
    }
  }

  function countDocumentsInTree(node: TreeNode): number {
    let count = 0;
    if (node.type === 'document') return 1;
    if (node.children) {
      for (const child of node.children) {
        count += countDocumentsInTree(child);
      }
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
        useUIStore.getState().setTrashCount(useUIStore.getState().trashCount + 1);
        toast.success('Moved to trash', 'Document can be restored from the Trash');
      }
      await loadTree();
      setDeleteConfirmOpen(false);
      setSelectedNode(null);
    } catch (err) {
      toast.error('Delete failed', getApiErrorMessage(err));
    }
  }

  function handleNewDocClick(path?: string) {
    setDefaultPath(path || '');
    setNewDocDialogOpen(true);
  }

  function handleNewFolderClick(path?: string) {
    setDefaultPath(path || '');
    setNewFolderDialogOpen(true);
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

  // --- Helpers ---

  function getNodeTooltip(node: TreeNode): string {
    const parts: string[] = [];
    if (node.type === 'folder' && node.description) parts.push(node.description);
    if (node.path) parts.push(`Path: ${node.path}`);
    if (node.children && node.children.length > 0) {
      parts.push(`${countDocumentsInTree(node)} document(s)`);
    }
    return parts.join(' \u2022 ');
  }

  // --- Render ---

  function renderNode(node: TreeNode, level = 0) {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const indent = level * INDENT_PER_LEVEL;
    const isDropTarget = dropTargetId === node.id;
    const isSelected = selectedIds.has(node.id);
    const tooltip = getNodeTooltip(node);

    return (
      <div key={node.id}>
        <div>
          <button
            onClick={(e) => handleNodeClick(node, e)}
            onContextMenu={(e) => handleContextMenu(e, node)}
            draggable={true}
            onDragStart={(e) => handleDragStart(e, node)}
            onDragOver={(e) => handleDragOver(e, node)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, node)}
            onDragEnd={handleDragEnd}
            title={tooltip}
            className={`w-full text-left px-3 py-2 hover:bg-muted rounded text-sm flex items-center gap-2 transition-colors ${
              isDropTarget ? overlayVariants.dropTarget : ''
            } ${isSelected ? 'bg-primary/10 ring-1 ring-primary/30' : ''} cursor-grab active:cursor-grabbing`}
            style={{ paddingLeft: `${indent + NODE_BASE_PADDING}px` }}
          >
            {hasChildren && (
              <span className="text-xs w-3">
                {isExpanded ? '\u25BC' : '\u25B6'}
              </span>
            )}
            {!hasChildren && <span className="w-3" />}
            {node.type === 'folder' && node.is_crate && (
              <Layers className={iconVariants.folderCrate} />
            )}
            {node.type === 'folder' && !node.is_crate && (
              isExpanded ? (
                <FolderOpen className={iconVariants.folder} />
              ) : (
                <Folder className={iconVariants.folder} />
              )
            )}
            {node.type === 'document' && (
              <FileText className={iconVariants.document} />
            )}
            <span className="flex-1 truncate">{node.name}</span>
            {node.type === 'folder' && hasChildren && (
              <span className="text-xs text-muted-foreground px-2 py-0.5 rounded bg-muted">
                {countDocumentsInTree(node)}
              </span>
            )}
            {node.type === 'folder' && !hasChildren && (
              <span className="text-xs text-muted-foreground px-2 py-0.5 rounded bg-muted/50 italic">
                empty
              </span>
            )}
            {node.type === 'folder' && node.is_crate && (() => {
              // Find generation status for this crate by checking all repo_urls
              const entry = Object.entries(generationStatus).find(
                ([repoUrl]) => repoUrl.includes(node.name)
              );
              if (!entry) return null;
              const [, jobStatus] = entry;
              if (jobStatus.status === 'running') {
                return <span title="Generating..."><Loader2 className="h-3 w-3 text-blue-500 animate-spin" /></span>;
              }
              if (jobStatus.status === 'queued') {
                return <span title="Queued for regeneration"><Clock className="h-3 w-3 text-amber-500" /></span>;
              }
              if (jobStatus.status === 'completed' && jobStatus.completed_at) {
                const date = new Date(jobStatus.completed_at);
                return (
                  <span className="text-xs text-muted-foreground" title={`Last generated: ${date.toLocaleString()}`}>
                    <CheckCircle2 className="h-3 w-3 text-green-500 inline" />
                  </span>
                );
              }
              if (jobStatus.status === 'failed') {
                const errorDetail = jobStatus.error_message
                  ? `Generation failed:\n${jobStatus.error_message}`
                  : 'Generation failed (no error details available)';
                return <span title={errorDetail}><XCircle className="h-3 w-3 text-red-500" /></span>;
              }
              return null;
            })()}
          </button>
          {node.type === 'folder' && node.description && (
            <div
              className="text-xs text-muted-foreground px-3 pb-1 italic"
              style={{ paddingLeft: `${indent + NODE_BASE_PADDING + 24}px` }}
            >
              {node.description}
            </div>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div>
            {node.children?.map(child => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
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
        {tree.map(node => renderNode(node))}

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
          onClose={() => setContextMenu(null)}
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
