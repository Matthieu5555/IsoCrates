'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { FileText } from 'lucide-react';

export interface GraphNodeData {
  label: string;
  path: string;
  keywords: string[];
  [key: string]: unknown;
}

/**
 * Custom reactflow node that displays a document in the dependency graph.
 *
 * Shows the document title, its folder path, and connects via handles
 * for incoming (top) and outgoing (bottom) dependency edges.
 */
export const GraphNode = memo(function GraphNode({ data }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-primary !w-2 !h-2" />
      <div className="rounded-lg border border-border bg-background shadow-sm px-4 py-3 min-w-[160px] max-w-[240px]">
        <div className="flex items-center gap-2 mb-1">
          <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
          <span className="text-sm font-medium truncate">{nodeData.label}</span>
        </div>
        {nodeData.path && (
          <div className="text-xs text-muted-foreground truncate">{nodeData.path}</div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-primary !w-2 !h-2" />
    </>
  );
});
