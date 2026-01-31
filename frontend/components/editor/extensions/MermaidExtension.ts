/**
 * Tiptap extension for live mermaid diagram preview within code blocks.
 *
 * When a code block's language is set to "mermaid", this extension renders
 * a live SVG preview below the editable text using the MermaidBlock component.
 * The code block remains editable; the preview updates on content change.
 *
 * Implementation: This uses a custom NodeView that wraps the standard CodeBlock.
 * It checks the `language` attribute and, if "mermaid", appends a preview div.
 *
 * Note: This is intentionally kept as a thin extension. The heavy rendering
 * logic lives in MermaidBlock.tsx, which is shared with the read-only renderer.
 */

import { CodeBlock } from '@tiptap/extension-code-block';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { MermaidCodeBlockView } from './MermaidCodeBlockView';

export const MermaidExtension = CodeBlock.extend({
  name: 'codeBlock',

  addNodeView() {
    return ReactNodeViewRenderer(MermaidCodeBlockView);
  },
});
