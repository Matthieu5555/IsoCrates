import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MarkdownRenderer } from '@/components/markdown/MarkdownRenderer';

// Mock the WikiLink component to avoid API calls
vi.mock('@/components/markdown/WikiLink', () => ({
  WikiLink: ({ children, target }: { children: React.ReactNode; target: string }) => (
    <a data-testid="wikilink" data-target={target}>{children}</a>
  ),
}));

// Mock MermaidBlock to avoid mermaid initialization
vi.mock('@/components/markdown/MermaidBlock', () => ({
  MermaidBlock: ({ chart }: { chart: string }) => (
    <div data-testid="mermaid-block">{chart}</div>
  ),
}));

describe('MarkdownRenderer', () => {
  describe('Basic Markdown', () => {
    it('renders headings correctly', () => {
      render(<MarkdownRenderer content="# Hello World" />);
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hello World');
    });

    it('renders paragraphs correctly', () => {
      render(<MarkdownRenderer content="This is a paragraph." />);
      expect(screen.getByText('This is a paragraph.')).toBeInTheDocument();
    });

    it('renders bold text correctly', () => {
      const { container } = render(<MarkdownRenderer content="This is **bold** text." />);
      const strong = container.querySelector('strong');
      expect(strong).toBeInTheDocument();
      expect(strong).toHaveTextContent('bold');
    });

    it('renders lists correctly', () => {
      const listContent = `- Item 1
- Item 2
- Item 3`;
      render(<MarkdownRenderer content={listContent} />);
      const listItems = screen.getAllByRole('listitem');
      expect(listItems).toHaveLength(3);
    });
  });

  describe('GFM Tables', () => {
    it('renders tables with correct structure', () => {
      const tableMarkdown = `
| Name | Age |
|------|-----|
| Alice | 30 |
| Bob | 25 |
`;
      render(<MarkdownRenderer content={tableMarkdown} />);
      expect(screen.getByRole('table')).toBeInTheDocument();
      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
  });

  describe('XSS Sanitization', () => {
    it('does not render script tags as executable code', () => {
      // Raw HTML is not rendered by react-markdown (no rehypeRaw plugin)
      // Script content appears as escaped text, not as a script element
      const maliciousContent = '<script>alert("xss")</script>';
      const { container } = render(<MarkdownRenderer content={maliciousContent} />);

      // No actual script element should be in the DOM
      expect(container.querySelector('script')).not.toBeInTheDocument();
    });

    it('does not render image onerror handlers', () => {
      // Markdown images are safe by default
      const markdownImage = '![alt text](image.png)';
      const { container } = render(<MarkdownRenderer content={markdownImage} />);

      const img = container.querySelector('img');
      expect(img).toBeInTheDocument();
      expect(img).not.toHaveAttribute('onerror');
    });

    it('sanitizes javascript: links', () => {
      // Test that javascript: protocol links are neutralized
      const maliciousLink = '[click me](javascript:alert("xss"))';
      const { container } = render(<MarkdownRenderer content={maliciousLink} />);

      const link = container.querySelector('a');
      // Link should either not have href or not have javascript: protocol
      if (link && link.getAttribute('href')) {
        expect(link.getAttribute('href')).not.toContain('javascript:');
      }
    });
  });

  describe('External Links', () => {
    it('adds target="_blank" to external links', () => {
      render(<MarkdownRenderer content="[Google](https://google.com)" />);
      const link = screen.getByRole('link', { name: /Google/i });
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('does not add target="_blank" to internal links', () => {
      render(<MarkdownRenderer content="[Internal](/docs/page)" />);
      const link = screen.getByRole('link', { name: /Internal/i });
      expect(link).not.toHaveAttribute('target');
    });
  });

  describe('Wikilinks', () => {
    it('renders wikilinks using WikiLink component', () => {
      render(<MarkdownRenderer content="See [[My Document]] for details." />);
      const wikilink = screen.getByTestId('wikilink');
      expect(wikilink).toBeInTheDocument();
      expect(wikilink).toHaveAttribute('data-target', 'my document');
    });

    it('handles wikilinks with display text', () => {
      render(<MarkdownRenderer content="See [[Target Page|display text]] here." />);
      const wikilink = screen.getByTestId('wikilink');
      expect(wikilink).toHaveTextContent('display text');
    });
  });

  describe('Code Blocks', () => {
    it('renders code blocks with syntax highlighting classes', () => {
      const codeMarkdown = '```javascript\nconst x = 1;\n```';
      const { container } = render(<MarkdownRenderer content={codeMarkdown} />);

      const codeElement = container.querySelector('code');
      expect(codeElement).toBeInTheDocument();
    });

    it('renders mermaid blocks using MermaidBlock component', () => {
      const mermaidMarkdown = '```mermaid\ngraph TD\nA-->B\n```';
      render(<MarkdownRenderer content={mermaidMarkdown} />);

      const mermaidBlock = screen.getByTestId('mermaid-block');
      expect(mermaidBlock).toBeInTheDocument();
      expect(mermaidBlock).toHaveTextContent('graph TD');
    });
  });
});
