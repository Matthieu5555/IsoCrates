export const dynamic = 'force-dynamic';

import { getDocumentVersions } from '@/lib/api/documents';
import Link from 'next/link';
import { badgeVariants, buttonVariants, containerVariants, linkVariants, statusBadgeVariants } from '@/lib/styles/button-variants';

export default async function VersionsListPage({
  params,
}: {
  params: { docId: string };
}) {
  const versions = await getDocumentVersions(params.docId);

  return (
    <div className={containerVariants.page}>
      <div className="mb-6">
        <Link
          href={`/docs/${params.docId}`}
          className={linkVariants.default}
        >
          ← Back to document
        </Link>
      </div>

      <h1 className="text-3xl font-bold mb-6">Version History</h1>

      <div className="space-y-4">
        {versions.map((version, index) => (
          <div
            key={version.version_id}
            className="border border-border rounded-lg p-4 hover:bg-muted/20"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className={version.author_type === 'ai' ? badgeVariants.authorAi : badgeVariants.authorHuman}>
                    {version.author_type.toUpperCase()}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {new Date(version.created_at).toLocaleString()}
                  </span>
                  {index === 0 && (
                    <span className={statusBadgeVariants.current}>
                      Current
                    </span>
                  )}
                </div>

                {version.author_metadata && (
                  <div className="text-xs text-muted-foreground space-y-1">
                    {version.author_metadata.model && (
                      <div>Model: {version.author_metadata.model}</div>
                    )}
                    {version.author_metadata.generator && (
                      <div>Generator: {version.author_metadata.generator}</div>
                    )}
                  </div>
                )}
              </div>

              <Link
                href={`/docs/${params.docId}/versions/${version.version_id}`}
                className={buttonVariants.primary}
              >
                View
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
