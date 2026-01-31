'use client';

import dynamic from 'next/dynamic';

const DependencyGraph = dynamic(
  () => import('@/components/graph/DependencyGraph').then((m) => m.DependencyGraph),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-96 text-muted-foreground text-sm">
        Loading graph...
      </div>
    ),
  },
);

/**
 * Graph view page: interactive visualization of document wikilink dependencies.
 *
 * Uses absolute positioning to fill the main content area because reactflow
 * requires a container with explicit dimensions. The negative margins cancel
 * the padding applied by AppShell's <main> element.
 */
export default function GraphPage() {
  return (
    <div className="absolute inset-0">
      <DependencyGraph />
    </div>
  );
}
