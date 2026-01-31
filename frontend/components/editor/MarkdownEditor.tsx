'use client';

import React, { useEffect, useCallback } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import { useRouter } from 'next/navigation';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Placeholder from '@tiptap/extension-placeholder';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import { Markdown } from 'tiptap-markdown';
import { EditorToolbar } from './EditorToolbar';
import { WikilinkExtension } from './extensions/WikilinkExtension';
import { markdownSerializerConfig } from '@/lib/editor/markdownSerializer';
import { resolveWikilink } from '@/lib/api/documents';
import { toast } from '@/lib/notifications/toast';

interface MarkdownEditorProps {
  /** Initial markdown content to load into the editor */
  content: string;
  /** Called with the current markdown string whenever content changes */
  onChange: (markdown: string) => void;
  /** Placeholder text shown when the editor is empty */
  placeholder?: string;
  /** When true, editor stretches to fill its container height */
  fullScreen?: boolean;
}

/**
 * Rich text editor that stores content as markdown.
 *
 * Built on Tiptap (ProseMirror), this component provides WYSIWYG editing
 * with a formatting toolbar while maintaining markdown as the serialization
 * format. The editor loads markdown via the tiptap-markdown extension, which
 * parses it into ProseMirror nodes on mount and serializes back to markdown
 * on every change via `editor.storage.markdown.getMarkdown()`.
 */
export function MarkdownEditor({ content, onChange, placeholder, fullScreen }: MarkdownEditorProps) {
  const router = useRouter();

  const handleWikilinkClick = useCallback(async (target: string) => {
    try {
      const docId = await resolveWikilink(target);
      if (docId) {
        router.push(`/docs/${docId}`);
      } else {
        toast.warning('Link Not Found', `Could not find document: ${target}`);
      }
    } catch {
      toast.error('Link Error', `Failed to resolve link: ${target}`);
    }
  }, [router]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({}),
      Underline,
      Table.configure({ resizable: true }),
      TableRow,
      TableCell,
      TableHeader,
      Placeholder.configure({
        placeholder: placeholder ?? 'Start writing...',
      }),
      WikilinkExtension.configure({
        onWikilinkClick: handleWikilinkClick,
      }),
      Markdown.configure({
        ...markdownSerializerConfig,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: `prose prose-slate dark:prose-invert max-w-none px-4 py-3 focus:outline-none ${
          fullScreen ? 'min-h-[calc(100vh-10rem)]' : 'min-h-[500px]'
        }`,
      },
    },
    onUpdate: ({ editor: ed }) => {
      const md = (ed.storage as any).markdown.getMarkdown();
      onChange(md);
    },
  });

  // Sync external content changes (e.g. reset on cancel)
  const setEditorContent = useCallback(
    (md: string) => {
      if (!editor) return;
      const currentMd = (editor.storage as any).markdown.getMarkdown();
      if (currentMd !== md) {
        editor.commands.setContent(md);
      }
    },
    [editor],
  );

  useEffect(() => {
    setEditorContent(content);
  }, [content, setEditorContent]);

  if (!editor) {
    return (
      <div className={`border border-border rounded-lg overflow-hidden ${fullScreen ? 'h-full' : ''}`}>
        <div className={`flex items-center justify-center text-muted-foreground text-sm ${
          fullScreen ? 'min-h-[calc(100vh-10rem)]' : 'min-h-[500px]'
        }`}>
          Loading editor...
        </div>
      </div>
    );
  }

  return (
    <div className={`border border-border rounded-lg overflow-hidden flex flex-col ${fullScreen ? 'h-full' : ''}`}>
      <EditorToolbar editor={editor} />
      <style>{`
        .ProseMirror table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        .ProseMirror th, .ProseMirror td { border: 1px solid hsl(var(--border)); padding: 0.5rem 0.75rem; min-width: 80px; }
        .ProseMirror th { background: hsl(var(--muted)); font-weight: 600; }
        .ProseMirror .selectedCell { background: hsl(var(--accent) / 0.3); }
        .ProseMirror .column-resize-handle { position: absolute; right: -2px; top: 0; bottom: 0; width: 4px; background: hsl(var(--primary)); cursor: col-resize; }
      `}</style>
      <div className={`overflow-y-auto ${fullScreen ? 'flex-1' : ''}`}>
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
