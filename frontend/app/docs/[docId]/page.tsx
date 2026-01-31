import { notFound } from 'next/navigation';
import { getDocument } from '@/lib/api/documents';
import { ApiError } from '@/lib/api/client';
import { DocumentView } from '@/components/document/DocumentView';

export default async function DocumentPage({
  params,
}: {
  params: { docId: string };
}) {
  try {
    const document = await getDocument(params.docId);
    return <DocumentView document={document} />;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}
