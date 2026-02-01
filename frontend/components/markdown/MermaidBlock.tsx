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
    return { theme: 'default' as const, securityLevel: 'strict' as const, startOnLoad: false };
  }

  const isDark = document.documentElement.classList.contains('dark');
  const isCustom = document.documentElement.classList.contains('custom');

  if (isCustom) {
    return {
      startOnLoad: false,
      theme: 'base' as const,
      securityLevel: 'strict' as const,
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
    securityLevel: 'strict' as const,
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
      <div className="rounded-md border border-border bg-muted/50 p-3 text-xs text-muted-foreground">
        <span>Diagram could not be rendered</span>
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
