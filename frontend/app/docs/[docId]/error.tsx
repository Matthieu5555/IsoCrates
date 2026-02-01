'use client';

import { useRouter } from 'next/navigation';
import { buttonVariants } from '@/lib/styles/button-variants';

export default function DocumentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  return (
    <div className="flex flex-col items-center justify-center h-[50vh] gap-4 text-center px-4">
      <h2 className="text-xl font-semibold">Document could not be loaded</h2>
      <p className="text-muted-foreground text-sm max-w-md">
        This document could not be loaded. Please try again.
      </p>
      <div className="flex gap-3">
        <button onClick={reset} className={buttonVariants.secondary}>
          Try again
        </button>
        <button onClick={() => router.push('/docs')} className={buttonVariants.primary}>
          Go to documents
        </button>
      </div>
    </div>
  );
}
