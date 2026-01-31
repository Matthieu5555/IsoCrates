'use client';

import React, { useEffect, useRef, useState } from 'react';

interface MermaidBlockProps {
  /** Raw mermaid diagram definition string */
  chart: string;
}

// Incrementing ID to ensure unique mermaid render targets
let mermaidIdCounter = 0;

/**
 * Renders a Mermaid diagram from its text definition.
 *
 * Dynamically imports the mermaid library to avoid bundling it in the
 * initial page load. Each instance gets a unique ID to prevent render
 * collisions when multiple diagrams are on the same page.
 *
 * Used by both the read-only MarkdownRenderer (via rehype component override)
 * and the Tiptap MermaidExtension for live preview in the editor.
 */
export function MermaidBlock({ chart }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [id] = useState(() => `mermaid-${++mermaidIdCounter}`);

  useEffect(() => {
    if (!chart.trim() || !containerRef.current) return;

    let cancelled = false;

    async function renderDiagram() {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'strict',
        });

        const { svg } = await mermaid.render(id, chart.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram');
        }
      }
    }

    renderDiagram();
    return () => { cancelled = true; };
  }, [chart, id]);

  if (error) {
    return (
      <div className="rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/30 p-4 text-sm text-red-600 dark:text-red-400">
        <p className="font-medium mb-1">Mermaid diagram error</p>
        <pre className="text-xs whitespace-pre-wrap">{error}</pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-4 flex justify-center overflow-x-auto"
    />
  );
}
