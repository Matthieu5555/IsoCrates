'use client';

import React, { memo } from 'react';
import { type NodeProps } from '@xyflow/react';
import { Folder } from 'lucide-react';

export interface GraphGroupData {
  label: string;
  color: string;
  isDimmed?: boolean;
  [key: string]: unknown;
}

export const GraphGroupNode = memo(function GraphGroupNode({ data }: NodeProps) {
  const groupData = data as unknown as GraphGroupData;
  const { isDimmed } = groupData;

  const containerClasses = [
    "rounded-xl border border-border/40 w-full h-full",
    isDimmed && "opacity-25",
  ].filter(Boolean).join(' ');

  return (
    <div
      className={containerClasses}
      style={{ backgroundColor: groupData.color, pointerEvents: 'none' }}
    >
      <div
        className="flex items-center gap-1.5 px-3 py-1.5"
        style={{ pointerEvents: 'auto' }}
      >
        <Folder className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs font-semibold text-muted-foreground">
          {groupData.label}
        </span>
      </div>
    </div>
  );
});
