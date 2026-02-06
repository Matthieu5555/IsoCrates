'use client';

import React, { memo, useMemo } from 'react';
import { FileText, Folder, FolderOpen, Layers, Loader2, Clock, CheckCircle2, XCircle } from 'lucide-react';
import type { TreeNode } from '@/types';
import { iconVariants, overlayVariants } from '@/lib/styles/button-variants';
import { INDENT_PER_LEVEL, NODE_BASE_PADDING } from '@/lib/config/tree-constants';

interface GenerationJobStatus {
  status: string;
  completed_at?: string;
  error_message?: string;
}

interface TreeNodeRowProps {
  node: TreeNode;
  level: number;
  expandedNodes: Set<string>;
  dropTargetId: string | null;
  selectedIds: Set<string>;
  generationStatus: Record<string, GenerationJobStatus>;
  onNodeClick: (node: TreeNode, e: React.MouseEvent) => void;
  onContextMenu: (e: React.MouseEvent, node: TreeNode) => void;
  onDragStart: (e: React.DragEvent, node: TreeNode) => void;
  onDragOver: (e: React.DragEvent, node: TreeNode) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent, node: TreeNode) => void;
  onDragEnd: (e: React.DragEvent) => void;
}

function countDocuments(node: TreeNode): number {
  if (node.type === 'document') return 1;
  let count = 0;
  if (node.children) {
    for (const child of node.children) {
      count += countDocuments(child);
    }
  }
  return count;
}

function getTooltip(node: TreeNode, docCount: number): string {
  const parts: string[] = [];
  if (node.type === 'folder' && node.description) parts.push(node.description);
  if (node.path) parts.push(`Path: ${node.path}`);
  if (node.children && node.children.length > 0) {
    parts.push(`${docCount} document(s)`);
  }
  return parts.join(' \u2022 ');
}

const GenerationBadge = memo(function GenerationBadge({
  node,
  generationStatus,
}: {
  node: TreeNode;
  generationStatus: Record<string, GenerationJobStatus>;
}) {
  if (node.type !== 'folder' || !node.is_crate) return null;

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
});

export const TreeNodeRow = memo(function TreeNodeRow({
  node,
  level,
  expandedNodes,
  dropTargetId,
  selectedIds,
  generationStatus,
  onNodeClick,
  onContextMenu,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
}: TreeNodeRowProps) {
  const isExpanded = expandedNodes.has(node.id);
  const isDropTarget = dropTargetId === node.id;
  const isSelected = selectedIds.has(node.id);
  const hasChildren = node.children && node.children.length > 0;
  const indent = level * INDENT_PER_LEVEL;

  const docCount = useMemo(() => countDocuments(node), [node]);
  const tooltip = useMemo(() => getTooltip(node, docCount), [node, docCount]);

  return (
    <div>
      <div>
        <button
          onClick={(e) => onNodeClick(node, e)}
          onContextMenu={(e) => onContextMenu(e, node)}
          draggable={true}
          onDragStart={(e) => onDragStart(e, node)}
          onDragOver={(e) => onDragOver(e, node)}
          onDragLeave={onDragLeave}
          onDrop={(e) => onDrop(e, node)}
          onDragEnd={onDragEnd}
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
              {docCount}
            </span>
          )}
          {node.type === 'folder' && !hasChildren && (
            <span className="text-xs text-muted-foreground px-2 py-0.5 rounded bg-muted/50 italic">
              empty
            </span>
          )}
          <GenerationBadge node={node} generationStatus={generationStatus} />
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
          {node.children?.map(child => (
            <TreeNodeRow
              key={child.id}
              node={child}
              level={level + 1}
              expandedNodes={expandedNodes}
              dropTargetId={dropTargetId}
              selectedIds={selectedIds}
              generationStatus={generationStatus}
              onNodeClick={onNodeClick}
              onContextMenu={onContextMenu}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onDragEnd={onDragEnd}
            />
          ))}
        </div>
      )}
    </div>
  );
});
