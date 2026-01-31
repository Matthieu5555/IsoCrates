'use client';

import React, { useState, useRef } from 'react';
import { type Editor } from '@tiptap/react';
import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Code,
  Quote,
  Minus,
  Undo,
  Redo,
  Table,
  Plus,
  Trash2,
  Columns,
  Rows,
  AtSign,
} from 'lucide-react';
import { WikilinkPicker } from './WikilinkPicker';

interface EditorToolbarProps {
  editor: Editor;
}

interface ToolbarButton {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  action: () => void;
  isActive: () => boolean;
}

/**
 * Formatting toolbar for the Tiptap editor.
 *
 * Provides buttons for common markdown formatting and an @ button that opens
 * a document search popover to insert [[wikilink]] references. The picker
 * leverages the backend search API so users can find any document quickly.
 */
export function EditorToolbar({ editor }: EditorToolbarProps) {
  const [wikilinkPickerOpen, setWikilinkPickerOpen] = useState(false);
  const wikilinkButtonRef = useRef<HTMLButtonElement>(null);

  const handleWikilinkSelect = (title: string) => {
    editor.chain().focus().insertWikilink(title).run();
  };

  const groups: ToolbarButton[][] = [
    // Text formatting
    [
      {
        icon: Bold,
        label: 'Bold',
        action: () => editor.chain().focus().toggleBold().run(),
        isActive: () => editor.isActive('bold'),
      },
      {
        icon: Italic,
        label: 'Italic',
        action: () => editor.chain().focus().toggleItalic().run(),
        isActive: () => editor.isActive('italic'),
      },
      {
        icon: Underline,
        label: 'Underline',
        action: () => editor.chain().focus().toggleUnderline().run(),
        isActive: () => editor.isActive('underline'),
      },
      {
        icon: Strikethrough,
        label: 'Strikethrough',
        action: () => editor.chain().focus().toggleStrike().run(),
        isActive: () => editor.isActive('strike'),
      },
    ],
    // Headings
    [
      {
        icon: Heading1,
        label: 'Heading 1',
        action: () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
        isActive: () => editor.isActive('heading', { level: 1 }),
      },
      {
        icon: Heading2,
        label: 'Heading 2',
        action: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
        isActive: () => editor.isActive('heading', { level: 2 }),
      },
      {
        icon: Heading3,
        label: 'Heading 3',
        action: () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
        isActive: () => editor.isActive('heading', { level: 3 }),
      },
    ],
    // Lists and blocks
    [
      {
        icon: List,
        label: 'Bullet List',
        action: () => editor.chain().focus().toggleBulletList().run(),
        isActive: () => editor.isActive('bulletList'),
      },
      {
        icon: ListOrdered,
        label: 'Ordered List',
        action: () => editor.chain().focus().toggleOrderedList().run(),
        isActive: () => editor.isActive('orderedList'),
      },
      {
        icon: Code,
        label: 'Code Block',
        action: () => editor.chain().focus().toggleCodeBlock().run(),
        isActive: () => editor.isActive('codeBlock'),
      },
      {
        icon: Quote,
        label: 'Blockquote',
        action: () => editor.chain().focus().toggleBlockquote().run(),
        isActive: () => editor.isActive('blockquote'),
      },
      {
        icon: Minus,
        label: 'Horizontal Rule',
        action: () => editor.chain().focus().setHorizontalRule().run(),
        isActive: () => false,
      },
    ],
    // Table operations
    [
      {
        icon: Table,
        label: 'Insert Table',
        action: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
        isActive: () => editor.isActive('table'),
      },
      ...(editor.isActive('table') ? [
        {
          icon: Columns,
          label: 'Add Column',
          action: () => editor.chain().focus().addColumnAfter().run(),
          isActive: () => false,
        },
        {
          icon: Rows,
          label: 'Add Row',
          action: () => editor.chain().focus().addRowAfter().run(),
          isActive: () => false,
        },
        {
          icon: Trash2,
          label: 'Delete Table',
          action: () => editor.chain().focus().deleteTable().run(),
          isActive: () => false,
        },
      ] : []),
    ],
    // History
    [
      {
        icon: Undo,
        label: 'Undo',
        action: () => editor.chain().focus().undo().run(),
        isActive: () => false,
      },
      {
        icon: Redo,
        label: 'Redo',
        action: () => editor.chain().focus().redo().run(),
        isActive: () => false,
      },
    ],
  ];

  return (
    <div className="flex items-center gap-1 flex-wrap border-b border-border px-2 py-1.5 bg-muted/30 sticky top-0 z-10">
      {groups.map((group, groupIndex) => (
        <React.Fragment key={groupIndex}>
          {groupIndex > 0 && (
            <div className="w-px h-6 bg-border mx-1" />
          )}
          {group.map((button) => {
            const Icon = button.icon;
            const active = button.isActive();
            return (
              <button
                key={button.label}
                type="button"
                onClick={button.action}
                title={button.label}
                className={`rounded p-1.5 transition-colors ${
                  active
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
        </React.Fragment>
      ))}

      {/* Wikilink / @ mention button */}
      <div className="w-px h-6 bg-border mx-1" />
      <button
        ref={wikilinkButtonRef}
        type="button"
        onClick={() => setWikilinkPickerOpen(!wikilinkPickerOpen)}
        title="Insert document link (@)"
        className={`rounded p-1.5 transition-colors ${
          wikilinkPickerOpen
            ? 'bg-primary/15 text-primary'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
        }`}
      >
        <AtSign className="h-4 w-4" />
      </button>

      <WikilinkPicker
        anchorRef={wikilinkButtonRef}
        open={wikilinkPickerOpen}
        onClose={() => setWikilinkPickerOpen(false)}
        onSelect={handleWikilinkSelect}
      />
    </div>
  );
}
