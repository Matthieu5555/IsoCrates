'use client';

import React from 'react';
import { ArrowDownUp, ZoomIn, ZoomOut, Maximize, Search, X } from 'lucide-react';
import { buttonVariants } from '@/lib/styles/button-variants';

interface GraphControlsProps {
  direction: 'TB' | 'LR';
  pathFilter: string;
  showAllNodes: boolean;
  nodeCount: number;
  totalNodes: number;
  showAllEdges: boolean;
  edgeCount: number;
  totalEdges: number;
  onToggleDirection: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onPathFilterChange: (value: string) => void;
  onToggleShowAllNodes: () => void;
  onToggleShowAllEdges: () => void;
}

/**
 * Control panel for the dependency graph.
 *
 * Provides buttons to toggle layout direction (top-to-bottom vs left-to-right),
 * zoom in/out, and fit the entire graph into the viewport.
 */
export function GraphControls({
  direction,
  pathFilter,
  showAllNodes,
  nodeCount,
  totalNodes,
  showAllEdges,
  edgeCount,
  totalEdges,
  onToggleDirection,
  onZoomIn,
  onZoomOut,
  onFitView,
  onPathFilterChange,
  onToggleShowAllNodes,
  onToggleShowAllEdges,
}: GraphControlsProps) {
  const isNodesLimited = nodeCount < totalNodes;
  const isEdgesLimited = edgeCount < totalEdges;

  return (
    <div className="absolute top-4 right-4 z-10 flex flex-col gap-2 rounded-lg border border-border bg-background/95 backdrop-blur-sm shadow-lg p-2">
      {/* Filter input */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={pathFilter}
          onChange={(e) => onPathFilterChange(e.target.value)}
          placeholder="Filter by path..."
          className="w-40 pl-8 pr-7 py-1.5 text-xs rounded-md border border-border bg-muted/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
        />
        {pathFilter && (
          <button
            onClick={() => onPathFilterChange('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            title="Clear filter"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Node count and show all toggle */}
      {totalNodes > 100 && (
        <>
          <div className="h-px bg-border" />
          <div className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1">Nodes</span>
            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-muted-foreground">
                {nodeCount}{isNodesLimited ? ` of ${totalNodes}` : ''}
              </span>
              <button
                onClick={onToggleShowAllNodes}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  showAllNodes
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted hover:bg-muted/80 text-muted-foreground'
                }`}
              >
                {showAllNodes ? 'Limited' : 'Show all'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Edge count and show all toggle */}
      {totalEdges > 50 && (
        <>
          <div className="h-px bg-border" />
          <div className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1">Edges</span>
            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-muted-foreground">
                {edgeCount}{isEdgesLimited ? ` of ${totalEdges}` : ''}
              </span>
              <button
                onClick={onToggleShowAllEdges}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  showAllEdges
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted hover:bg-muted/80 text-muted-foreground'
                }`}
              >
                {showAllEdges ? 'Limited' : 'Show all'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Divider */}
      <div className="h-px bg-border" />

      {/* Layout toggle */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1">Layout</span>
        <button
          onClick={onToggleDirection}
          title={`Layout: ${direction === 'TB' ? 'Top to Bottom' : 'Left to Right'}`}
          className={`${buttonVariants.icon} flex items-center gap-2 text-sm`}
        >
          <ArrowDownUp className="h-4 w-4" />
          <span className="text-xs text-muted-foreground">{direction === 'TB' ? 'Vertical' : 'Horizontal'}</span>
        </button>
      </div>

      {/* Divider */}
      <div className="h-px bg-border" />

      {/* Zoom controls */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium px-1">Zoom</span>
        <div className="flex items-center gap-1">
          <button onClick={onZoomOut} title="Zoom out" className={buttonVariants.icon}>
            <ZoomOut className="h-4 w-4" />
          </button>
          <button onClick={onZoomIn} title="Zoom in" className={buttonVariants.icon}>
            <ZoomIn className="h-4 w-4" />
          </button>
          <button onClick={onFitView} title="Fit to view" className={buttonVariants.icon}>
            <Maximize className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
