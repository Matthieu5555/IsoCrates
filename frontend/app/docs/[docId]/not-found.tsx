import Link from 'next/link';

export default function DocumentNotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-[50vh] gap-4 text-center px-4">
      <h2 className="text-xl font-semibold">Document not found</h2>
      <p className="text-muted-foreground text-sm max-w-md">
        This document may have been deleted or the link may be incorrect.
      </p>
      <Link
        href="/docs"
        className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        Go to documents
      </Link>
    </div>
  );
}
