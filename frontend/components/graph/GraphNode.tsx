'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';

export interface GraphNodeData {
  label: string;
  path: string;
  keywords: string[];
  direction: 'TB' | 'LR';
  isFocused?: boolean;
  isDimmed?: boolean;
  [key: string]: unknown;
}

/**
 * Simplified reactflow node for performance with large graphs.
 * Single div with title only, minimal DOM elements.
 */
export const GraphNode = memo(function GraphNode({ data }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;
  const isHorizontal = nodeData.direction === 'LR';
  const { isFocused, isDimmed } = nodeData;

  return (
    <div
      className={`rounded-md border border-border bg-background px-3 py-2 text-sm font-medium truncate min-w-[120px] max-w-[200px] cursor-pointer will-change-transform ${
        isFocused ? 'ring-2 ring-primary shadow-md' : ''
      } ${isDimmed ? 'opacity-25' : ''}`}
    >
      <Handle
        type="target"
        position={isHorizontal ? Position.Left : Position.Top}
        className={`!w-1.5 !h-1.5 ${isDimmed ? '!bg-muted-foreground' : '!bg-primary'}`}
      />
      {nodeData.label}
      <Handle
        type="source"
        position={isHorizontal ? Position.Right : Position.Bottom}
        className={`!w-1.5 !h-1.5 ${isDimmed ? '!bg-muted-foreground' : '!bg-primary'}`}
      />
    </div>
  );
});
