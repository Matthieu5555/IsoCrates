'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { FileText } from 'lucide-react';

export interface GraphNodeData {
  label: string;
  path: string;
  keywords: string[];
  direction: 'TB' | 'LR';
  [key: string]: unknown;
}

/**
 * Custom reactflow node that displays a document in the dependency graph.
 *
 * Shows the document title, its folder path, and connects via handles
 * whose positions adapt to the current layout direction (TB or LR).
 */
export const GraphNode = memo(function GraphNode({ data }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;
  const isHorizontal = nodeData.direction === 'LR';

  return (
    <>
      <Handle
        type="target"
        position={isHorizontal ? Position.Left : Position.Top}
        className="!bg-primary !w-2 !h-2"
      />
      <div className="rounded-lg border border-border bg-background shadow-sm px-4 py-3 min-w-[160px] max-w-[240px] cursor-pointer">
        <div className="flex items-center gap-2 mb-1">
          <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
          <span className="text-sm font-medium truncate">{nodeData.label}</span>
        </div>
        {nodeData.path && (
          <div className="text-xs text-muted-foreground truncate">{nodeData.path}</div>
        )}
      </div>
      <Handle
        type="source"
        position={isHorizontal ? Position.Right : Position.Bottom}
        className="!bg-primary !w-2 !h-2"
      />
    </>
  );
});
