'use client';

import React from 'react';
import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { MermaidBlock } from '@/components/markdown/MermaidBlock';

/**
 * Custom NodeView for code blocks that adds a live mermaid preview
 * when the language attribute is "mermaid".
 *
 * For non-mermaid code blocks, renders the standard code block UI.
 */
export function MermaidCodeBlockView({ node }: NodeViewProps) {
  const language = (node.attrs as Record<string, unknown>).language as string | null;
  const isMermaid = language === 'mermaid';
  const textContent = node.textContent as string;

  return (
    <NodeViewWrapper className="relative">
      <pre className="rounded-md bg-muted p-4 overflow-x-auto">
        <NodeViewContent as="div" className={language ? `language-${language} font-mono text-sm` : 'font-mono text-sm'} />
      </pre>
      {isMermaid && textContent.trim() && (
        <div className="border border-border rounded-md mt-2 p-4 bg-background">
          <div className="text-xs text-muted-foreground mb-2 font-medium">Preview</div>
          <MermaidBlock chart={textContent} />
        </div>
      )}
    </NodeViewWrapper>
  );
}
