'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { getDocumentVersions } from '@/lib/api/documents';
import type { Version } from '@/types';
import { badgeVariants, linkVariants, scrollContainerVariants } from '@/lib/styles/button-variants';
import { getApiErrorMessage } from '@/lib/api/client';
import { toast } from '@/lib/notifications/toast';

interface VersionHistoryProps {
  docId: string;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  }) + ' ' + date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
}

export function VersionHistory({ docId }: VersionHistoryProps) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    loadVersions();
  }, [docId]);

  async function loadVersions() {
    try {
      setLoading(true);
      setError(null);
      const data = await getDocumentVersions(docId);
      setVersions(data);
    } catch (err) {
      console.error('Failed to load versions:', err);
      const message = getApiErrorMessage(err);
      setError(message);
      toast.error('Failed to Load Versions', message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading versions...</div>;
  }

  if (error) {
    return (
      <div className="text-sm text-muted-foreground">
        Could not load version history
      </div>
    );
  }

  if (versions.length === 0) {
    return <div className="text-sm text-muted-foreground">No version history available</div>;
  }

  return (
    <div className="mt-8 pt-6 border-t border-border">
      <h2 className="text-lg font-semibold mb-4">Version History</h2>
      <div className={`space-y-3 ${scrollContainerVariants.maxHeight50}`}>
        {versions.map((version, index) => (
          <div
            key={version.version_id}
            className="flex items-center gap-3 text-sm px-3 py-2.5 hover:bg-muted/50 rounded transition-colors"
          >
            <span className={version.author_type === 'ai' ? badgeVariants.authorAi : badgeVariants.authorHuman}>
              {version.author_type}
            </span>
            <span className="text-muted-foreground">
              {mounted ? formatDate(version.created_at) : 'Loading...'}
            </span>
            {version.author_metadata?.model && (
              <span className="text-xs text-muted-foreground">
                ({version.author_metadata.model})
              </span>
            )}
            <Link
              href={`/docs/${docId}/versions/${version.version_id}`}
              className={`ml-auto ${linkVariants.external} text-xs`}
            >
              View
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
