'use client';

import React from 'react';
import { ArrowDownUp, ZoomIn, ZoomOut, Maximize } from 'lucide-react';

interface GraphControlsProps {
  direction: 'TB' | 'LR';
  onToggleDirection: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
}

/**
 * Control panel for the dependency graph.
 *
 * Provides buttons to toggle layout direction (top-to-bottom vs left-to-right),
 * zoom in/out, and fit the entire graph into the viewport.
 */
export function GraphControls({
  direction,
  onToggleDirection,
  onZoomIn,
  onZoomOut,
  onFitView,
}: GraphControlsProps) {
  const buttonClass =
    'rounded p-2 hover:bg-accent text-muted-foreground hover:text-foreground transition-colors';

  return (
    <div className="absolute top-4 right-4 z-10 flex flex-col gap-1 rounded-lg border border-border bg-background shadow-sm p-1">
      <button
        onClick={onToggleDirection}
        title={`Layout: ${direction === 'TB' ? 'Top to Bottom' : 'Left to Right'}`}
        className={buttonClass}
      >
        <ArrowDownUp className="h-4 w-4" />
      </button>
      <div className="h-px bg-border" />
      <button onClick={onZoomIn} title="Zoom in" className={buttonClass}>
        <ZoomIn className="h-4 w-4" />
      </button>
      <button onClick={onZoomOut} title="Zoom out" className={buttonClass}>
        <ZoomOut className="h-4 w-4" />
      </button>
      <button onClick={onFitView} title="Fit view" className={buttonClass}>
        <Maximize className="h-4 w-4" />
      </button>
    </div>
  );
}
