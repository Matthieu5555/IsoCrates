'use client';

import { buttonVariants } from '@/lib/styles/button-variants';

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-[50vh] gap-4 text-center px-4">
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="text-muted-foreground text-sm max-w-md">
        An unexpected error occurred. Please try again.
      </p>
      <button onClick={reset} className={buttonVariants.primary}>
        Try again
      </button>
    </div>
  );
}
