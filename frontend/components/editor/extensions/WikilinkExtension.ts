/**
 * Tiptap extension for wikilink syntax: [[target]].
 *
 * Registers a custom inline node that:
 * - Parses [[target]] from markdown via an input rule
 * - Renders as a styled inline element in the editor
 * - Serializes back to [[target]] in markdown output
 * - Supports click-to-navigate via the existing wikilink resolution API
 *
 * This extension works with the tiptap-markdown extension by registering
 * custom markdown parse/serialize rules so that wikilinks survive the
 * markdown → ProseMirror → markdown round-trip without corruption.
 */

import { Node, mergeAttributes, InputRule } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

export interface WikilinkOptions {
  /** Called when a wikilink is clicked in the editor. Receives the target string. */
  onWikilinkClick?: (target: string) => void;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    wikilink: {
      insertWikilink: (target: string) => ReturnType;
    };
  }
}

export const WikilinkExtension = Node.create<WikilinkOptions>({
  name: 'wikilink',

  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addOptions() {
    return {
      onWikilinkClick: undefined,
    };
  },

  addAttributes() {
    return {
      target: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-target'),
        renderHTML: (attributes) => ({
          'data-target': attributes.target,
          'data-wikilink': '',
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-wikilink]',
        getAttrs: (element) => {
          const el = element as HTMLElement;
          return { target: el.getAttribute('data-target') };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        class: 'wikilink-node',
        style:
          'color: var(--link); text-decoration: underline; cursor: pointer; padding: 0 2px;',
      }),
      `[[${HTMLAttributes['data-target']}]]`,
    ];
  },

  addCommands() {
    return {
      insertWikilink:
        (target: string) =>
        ({ chain }) =>
          chain().insertContent({ type: this.name, attrs: { target } }).run(),
    };
  },

  addInputRules() {
    // When the user types [[something]] and the closing ]], replace with a wikilink node
    return [
      new InputRule({
        find: /\[\[([^\]]+)\]\]$/,
        handler: ({ state, range, match }) => {
          const target = match[1];
          const node = this.type.create({ target });
          const tr = state.tr.replaceWith(range.from, range.to, node);
          // Add a space after the wikilink so the cursor can continue typing
          tr.insertText(' ', tr.mapping.map(range.to));
          return;
        },
      }),
    ];
  },

  addProseMirrorPlugins() {
    const { onWikilinkClick } = this.options;
    return [
      new Plugin({
        key: new PluginKey('wikilinkClick'),
        props: {
          handleClick(view, pos, event) {
            const { state } = view;
            const node = state.doc.nodeAt(pos);
            if (node?.type.name === 'wikilink' && onWikilinkClick) {
              event.preventDefault();
              onWikilinkClick(node.attrs.target);
              return true;
            }
            return false;
          },
        },
      }),
    ];
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: any, node: any) {
          state.write(`[[${node.attrs.target}]]`);
        },
        parse: {
          setup(markdownit: any) {
            // Register an inline rule that tokenizes [[target]] into a wikilink token.
            // markdown-it processes this before any other inline rules, converting
            // the raw text into structured tokens that the render rule below turns
            // into <span data-wikilink data-target="..."> elements. ProseMirror then
            // maps those elements to wikilink nodes via the parseHTML() spec above.
            markdownit.inline.ruler.push('wikilink', (state: any, silent: boolean) => {
              const src = state.src.slice(state.pos);
              const match = src.match(/^\[\[([^\]]+)\]\]/);
              if (!match) return false;
              if (!silent) {
                const token = state.push('wikilink', 'span', 0);
                token.attrs = [['data-wikilink', ''], ['data-target', match[1]]];
                token.content = `[[${match[1]}]]`;
              }
              state.pos += match[0].length;
              return true;
            });

            markdownit.renderer.rules.wikilink = (tokens: any[], idx: number) => {
              const token = tokens[idx];
              const target = token.attrs?.find((a: string[]) => a[0] === 'data-target')?.[1] ?? '';
              return `<span data-wikilink="" data-target="${target}">[[${target}]]</span>`;
            };
          },
        },
      },
    };
  },
});
