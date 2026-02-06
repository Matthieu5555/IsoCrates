'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkWikiLink from 'remark-wiki-link';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import { ExternalLink } from 'lucide-react';
import { WikiLink } from './WikiLink';
import { MermaidBlock } from './MermaidBlock';

/**
 * Custom sanitization schema based on GitHub's defaults.
 * Allows additional elements needed for syntax highlighting and search snippets.
 */
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames || []),
    'mark',  // For FTS search result highlighting
  ],
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code || []), 'className'],
    span: [...(defaultSchema.attributes?.span || []), 'className'],
    mark: [],  // Allow <mark> with no special attributes
    a: [...(defaultSchema.attributes?.a || []), 'className', 'href'],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href || []), '#wiki'],
  },
};

interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders markdown content to styled HTML with support for:
 * - GitHub Flavored Markdown (tables, strikethrough, task lists)
 * - Wikilinks ([[target]] syntax, resolved via API)
 * - Mermaid diagrams (```mermaid code blocks rendered as SVG)
 * - Syntax-highlighted code blocks
 *
 * Mermaid handling: The `pre` component checks whether its child `code` element
 * has a mermaid language class. If so, it renders a MermaidBlock instead of the
 * default pre/code wrapper. This avoids the issue of react-markdown always
 * wrapping `code` in `pre` — we intercept at the `pre` level rather than the
 * `code` level to avoid nested DOM problems.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="prose prose-slate dark:prose-invert max-w-none px-4">
      <ReactMarkdown
        remarkPlugins={[
          remarkGfm,
          [
            remarkWikiLink,
            {
              pageResolver: (name: string) => [name.replace(/ /g, '-').toLowerCase()],
              hrefTemplate: (permalink: string) => `#wiki:${permalink}`,
              aliasDivider: '|',
            },
          ],
        ]}
        rehypePlugins={[rehypeHighlight, [rehypeSanitize, sanitizeSchema]]}
        components={{
          a: ({ node, children, href, ...props }) => {
            if (href?.startsWith('#wiki:')) {
              const target = href.replace('#wiki:', '').replace(/-/g, ' ');
              return <WikiLink target={target}>{children}</WikiLink>;
            }
            const isExternal = href?.startsWith('http://') || href?.startsWith('https://');
            if (isExternal) {
              return (
                <a href={href} target="_blank" rel="noopener noreferrer"
                   className="inline-flex items-center gap-0.5" {...props}>
                  {children}
                  <ExternalLink className="inline h-3 w-3 opacity-50 shrink-0" />
                </a>
              );
            }
            return <a href={href} {...props}>{children}</a>;
          },
          pre: ({ node, children, ...props }) => {
            // react-markdown wraps code blocks in <pre><code>...</code></pre>.
            // We intercept here to detect mermaid blocks and render them as diagrams.
            const childArray = React.Children.toArray(children);
            if (childArray.length === 1) {
              const child = childArray[0] as React.ReactElement;
              const className = child?.props?.className as string | undefined;
              if (className && /language-mermaid/.test(className)) {
                const chart = String(child.props.children ?? '').replace(/\n$/, '');
                return <MermaidBlock chart={chart} />;
              }
            }
            return <pre {...props}>{children}</pre>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
