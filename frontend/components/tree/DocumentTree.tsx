'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, FileText, Folder, FolderOpen, Layers, RefreshCw, Clock, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { getTree, getTrash, deleteDocument, createDocument, moveFolder, moveDocument, createFolderMetadata, deleteFolder, type CreateDocumentData, type CreateFolderMetadataData } from '@/lib/api/documents';
import { fetchApi } from '@/lib/api/client';
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

export function DocumentTree() {
  const router = useRouter();
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TreeNode;
  } | null>(null);

  const [newDocDialogOpen, setNewDocDialogOpen] = useState(false);
  const [newFolderDialogOpen, setNewFolderDialogOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteFolderDialogOpen, setDeleteFolderDialogOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<TreeNode | null>(null);
  const [defaultPath, setDefaultPath] = useState('');
  const [draggedNode, setDraggedNode] = useState<TreeNode | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [rootDropActive, setRootDropActive] = useState(false);
  const [movingFolder, setMovingFolder] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

  // Generation job status per crate (keyed by crate path)
  const [generationStatus, setGenerationStatus] = useState<Record<string, {
    status: string;
    completed_at?: string;
  }>>({});

  useEffect(() => {
    loadTree();
  }, []);

  async function loadTree() {
    try {
      setLoading(true);
      const data = await getTree();
      setTree(data);
      const firstLevel = new Set(data.map(node => node.id));
      setExpandedNodes(firstLevel);

      // Fetch generation status for crate nodes
      fetchGenerationStatus(data);

      // Fetch trash count for floating indicator
      getTrash().then(items => useUIStore.getState().setTrashCount(items.length)).catch(() => {});
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load tree';
      setError(message);
      toast.error('Failed to load tree', message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchGenerationStatus(nodes: TreeNode[]) {
    // Find crate-level nodes and fetch their latest generation job
    try {
      const jobs = await fetchApi<Array<{
        id: string;
        repo_url: string;
        status: string;
        completed_at?: string;
      }>>('/api/jobs?limit=50');

      const statusMap: Record<string, { status: string; completed_at?: string }> = {};
      for (const job of jobs) {
        // Map job to crate by matching repo_url in the tree
        // Use the first (most recent) job per repo_url
        if (!statusMap[job.repo_url]) {
          statusMap[job.repo_url] = {
            status: job.status,
            completed_at: job.completed_at,
          };
        }
      }
      setGenerationStatus(statusMap);
    } catch {
      // Generation jobs endpoint may not exist yet — ignore silently
    }
  }

  function toggleNode(nodeId: string) {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }

  function handleNodeClick(node: TreeNode, e?: React.MouseEvent) {
    // Ctrl/Cmd+click toggles selection for documents
    if (e && (e.ctrlKey || e.metaKey) && node.type === 'document') {
      setSelectedIds(prev => {
        const next = new Set(prev);
        if (next.has(node.id)) next.delete(node.id);
        else next.add(node.id);
        return next;
      });
      return;
    }

    if (node.type === 'document') {
      if (selectedIds.size > 0) {
        // If there's an active selection, clear it on plain click
        setSelectedIds(new Set());
      }
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
      toast.error('Delete failed', (err as Error).message);
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
      toast.error('Delete failed', (err as Error).message);
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
      toast.error('Create failed', (err as Error).message);
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

  // --- Drag and drop ---

  function validateDrop(dragged: TreeNode, target: TreeNode): { valid: boolean; reason?: string } {
    if (dragged.id === target.id) {
      return { valid: false, reason: "Can't drop on itself" };
    }
    if (target.type !== 'folder') {
      return { valid: false, reason: 'Can only drop into folders' };
    }
    if (isAncestor(dragged, target)) {
      return { valid: false, reason: "Can't drop folder into its subfolder" };
    }
    return { valid: true };
  }

  function isAncestor(potentialParent: TreeNode, node: TreeNode): boolean {
    if (!potentialParent.children) return false;
    for (const child of potentialParent.children) {
      if (child.id === node.id) return true;
      if (isAncestor(child, node)) return true;
    }
    return false;
  }

  function handleDragStart(e: React.DragEvent, node: TreeNode) {
    setDraggedNode(node);
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDragOver(e: React.DragEvent, node: TreeNode) {
    if (!draggedNode) return;
    const validation = validateDrop(draggedNode, node);
    if (validation.valid) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDropTargetId(node.id);
      setRootDropActive(false);
    } else {
      e.dataTransfer.dropEffect = 'none';
    }
  }

  function handleDragLeave() {
    setDropTargetId(null);
  }

  // Root-level drop zone: dropping on the tree background moves to root
  function handleRootDragOver(e: React.DragEvent) {
    if (!draggedNode) return;
    // Only activate if not hovering over a specific node
    if (dropTargetId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setRootDropActive(true);
  }

  function handleRootDragLeave(e: React.DragEvent) {
    // Only deactivate if leaving the container entirely
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const { clientX, clientY } = e;
    if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
      setRootDropActive(false);
    }
  }

  async function handleRootDrop(e: React.DragEvent) {
    e.preventDefault();
    setRootDropActive(false);
    setDropTargetId(null);

    if (!draggedNode) return;

    const sourcePath = draggedNode.path || '';
    const itemName = sourcePath.split('/').filter(p => p).pop() || draggedNode.name;

    // Already at root level
    if (!sourcePath.includes('/') && draggedNode.type === 'folder') {
      setDraggedNode(null);
      return;
    }

    setMovingFolder(true);
    try {
      if (draggedNode.type === 'document') {
        // Move document to root (empty path means top-level)
        await moveDocument(draggedNode.id, '');
        toast.success('Moved', `Document moved to root`);
      } else {
        // Move folder to root level — target path is just the folder name
        await moveFolder(sourcePath, itemName);
        toast.success('Moved', `Folder moved to root`);
      }
      await loadTree();
    } catch (err) {
      toast.error('Move failed', (err as Error).message);
    } finally {
      setMovingFolder(false);
      setDraggedNode(null);
    }
  }

  async function handleDrop(e: React.DragEvent, targetNode: TreeNode) {
    e.preventDefault();
    e.stopPropagation();
    setDropTargetId(null);
    setRootDropActive(false);

    if (!draggedNode) return;

    const validation = validateDrop(draggedNode, targetNode);
    if (!validation.valid) {
      toast.warning('Cannot drop here', validation.reason || 'Invalid drop target');
      setDraggedNode(null);
      return;
    }

    setMovingFolder(true);
    try {
      if (draggedNode.type === 'document') {
        // Move document into target folder
        const targetPath = targetNode.path || '';
        await moveDocument(draggedNode.id, targetPath);
        toast.success('Moved', 'Document moved');
      } else {
        // Move folder into target folder
        const sourcePath = draggedNode.path || '';
        const folderName = sourcePath.split('/').filter(p => p).pop() || draggedNode.name;
        const targetPath = targetNode.path
          ? `${targetNode.path}/${folderName}`
          : folderName;

        if (sourcePath === targetPath) {
          setDraggedNode(null);
          setMovingFolder(false);
          return;
        }

        const result = await moveFolder(sourcePath, targetPath);
        toast.success('Moved', `${result.affected_documents} document(s) updated`);
      }

      await loadTree();

      if (targetNode.type === 'folder') {
        setExpandedNodes(prev => new Set([...Array.from(prev), targetNode.id]));
      }
    } catch (err) {
      toast.error('Move failed', (err as Error).message);
    } finally {
      setMovingFolder(false);
      setDraggedNode(null);
    }
  }

  function handleDragEnd() {
    setDraggedNode(null);
    setDropTargetId(null);
    setRootDropActive(false);
  }

  function getNodeTooltip(node: TreeNode): string {
    const parts: string[] = [];
    if (node.type === 'folder' && node.description) parts.push(node.description);
    if (node.path) parts.push(`Path: ${node.path}`);
    if (node.children && node.children.length > 0) {
      parts.push(`${countDocumentsInTree(node)} document(s)`);
    }
    return parts.join(' \u2022 ');
  }

  function renderNode(node: TreeNode, level = 0) {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const indent = level * 16;
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
            style={{ paddingLeft: `${indent + 12}px` }}
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
                return <Loader2 className="h-3 w-3 text-blue-500 animate-spin" title="Generating..." />;
              }
              if (jobStatus.status === 'queued') {
                return <Clock className="h-3 w-3 text-amber-500" title="Queued for regeneration" />;
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
                return <XCircle className="h-3 w-3 text-red-500" title="Generation failed" />;
              }
              return null;
            })()}
          </button>
          {node.type === 'folder' && node.description && (
            <div
              className="text-xs text-muted-foreground px-3 pb-1 italic"
              style={{ paddingLeft: `${indent + 12 + 24}px` }}
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
        <div className="text-sm text-red-600 mb-2">Error: {error}</div>
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
        onClearSelection={() => setSelectedIds(new Set())}
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
            setSelectedIds(new Set());
            await loadTree();
          } catch {
            toast.error('Batch move failed', 'An unexpected error occurred');
          }
        }}
      />
    </div>
  );
}
