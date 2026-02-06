export const dynamic = 'force-dynamic';

import { getVersion } from '@/lib/api/documents';
import Link from 'next/link';
import { MarkdownRenderer } from '@/components/markdown/MarkdownRenderer';

export default async function VersionPage({
  params,
}: {
  params: { docId: string; versionId: string };
}) {
  const version = await getVersion(params.docId, params.versionId);

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="mb-6 flex items-center gap-4">
        <Link
          href={`/docs/${params.docId}`}
          className="text-blue-600 hover:underline text-sm"
        >
          ← Back to current version
        </Link>
        <Link
          href={`/docs/${params.docId}/versions`}
          className="text-blue-600 hover:underline text-sm"
        >
          View all versions
        </Link>
      </div>

      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
        <div className="flex items-center gap-3">
          <span className={`px-2 py-1 rounded text-xs font-medium ${
            version.author_type === 'ai'
              ? 'bg-purple-100 text-purple-700'
              : 'bg-orange-100 text-orange-700'
          }`}>
            {version.author_type.toUpperCase()}
          </span>
          <span className="text-sm font-medium">
            Historical Version
          </span>
          <span className="text-sm text-muted-foreground">
            {new Date(version.created_at).toLocaleString()}
          </span>
        </div>
        {version.author_metadata && (
          <div className="mt-2 text-xs text-muted-foreground">
            {version.author_metadata.model && (
              <span className="mr-4">Model: {version.author_metadata.model}</span>
            )}
            {version.author_metadata.generator && (
              <span>Generator: {version.author_metadata.generator}</span>
            )}
          </div>
        )}
      </div>

      <MarkdownRenderer content={version.content} />

      <div className="mt-8 pt-6 border-t border-border">
        <table className="w-full text-sm">
          <tbody>
            <tr className="border-b border-border">
              <td className="py-2 font-medium text-muted-foreground">Version ID</td>
              <td className="py-2 font-mono text-xs">{version.version_id}</td>
            </tr>
            <tr className="border-b border-border">
              <td className="py-2 font-medium text-muted-foreground">Content Hash</td>
              <td className="py-2 font-mono text-xs">{version.content_hash}</td>
            </tr>
            <tr className="border-b border-border">
              <td className="py-2 font-medium text-muted-foreground">Author Type</td>
              <td className="py-2">{version.author_type}</td>
            </tr>
            <tr>
              <td className="py-2 font-medium text-muted-foreground">Created At</td>
              <td className="py-2">{new Date(version.created_at).toLocaleString()}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
