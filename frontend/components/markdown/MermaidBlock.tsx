'use client';

import React, { useEffect, useRef, useState } from 'react';

interface MermaidBlockProps {
  /** Raw mermaid diagram definition string */
  chart: string;
}

// Incrementing ID to ensure unique mermaid render targets
let mermaidIdCounter = 0;

/** Read a CSS custom property as HSL values and convert to hex. */
function cssVarToHex(varName: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
  if (!raw) return fallback;

  const [h, sRaw, lRaw] = raw.split(/\s+/);
  const s = parseFloat(sRaw) / 100;
  const l = parseFloat(lRaw) / 100;

  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + parseFloat(h) / 30) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function getMermaidConfig() {
  if (typeof document === 'undefined') {
    return { theme: 'default' as const, securityLevel: 'loose' as const, startOnLoad: false, suppressErrorRendering: true };
  }

  const isDark = document.documentElement.classList.contains('dark');
  const isCustom = document.documentElement.classList.contains('custom');

  if (isCustom) {
    return {
      startOnLoad: false,
      theme: 'base' as const,
      securityLevel: 'loose' as const,
      suppressErrorRendering: true,
      themeVariables: {
        primaryColor: cssVarToHex('--primary', '#6366f1'),
        primaryTextColor: cssVarToHex('--primary-foreground', '#ffffff'),
        primaryBorderColor: cssVarToHex('--border', '#e2e8f0'),
        lineColor: cssVarToHex('--foreground', '#334155'),
        secondaryColor: cssVarToHex('--secondary', '#f1f5f9'),
        tertiaryColor: cssVarToHex('--muted', '#f1f5f9'),
        background: cssVarToHex('--background', '#ffffff'),
        textColor: cssVarToHex('--foreground', '#334155'),
        noteBkgColor: cssVarToHex('--muted', '#f1f5f9'),
        fontFamily: 'inherit',
      },
    };
  }

  return {
    startOnLoad: false,
    theme: isDark ? 'dark' as const : 'default' as const,
    securityLevel: 'loose' as const,
    suppressErrorRendering: true,
  };
}

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
        mermaid.initialize(getMermaidConfig());

        // Pre-validate syntax to catch errors before rendering
        await mermaid.parse(chart.trim());

        const { svg } = await mermaid.render(id, chart.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Failed to render diagram';
          console.warn('[MermaidBlock] Diagram render failed:', message);
          setError(message);
        }
      }
    }

    renderDiagram();
    return () => { cancelled = true; };
  }, [chart, id]);

  if (error) {
    return (
      <div className="my-4 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30">
        <div className="flex items-center gap-2 border-b border-amber-200 px-3 py-2 dark:border-amber-900">
          <svg className="h-4 w-4 text-amber-600 dark:text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium text-amber-800 dark:text-amber-200">
            Diagram syntax error
          </span>
        </div>
        <div className="px-3 py-2">
          <p className="text-xs text-amber-700 dark:text-amber-300 font-mono whitespace-pre-wrap">
            {error}
          </p>
        </div>
        <details className="border-t border-amber-200 dark:border-amber-900">
          <summary className="cursor-pointer px-3 py-2 text-xs text-amber-600 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/30">
            Show source
          </summary>
          <pre className="max-h-40 overflow-auto bg-amber-100/50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
            <code>{chart}</code>
          </pre>
        </details>
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
