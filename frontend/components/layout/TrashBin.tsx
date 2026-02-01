'use client';

import { useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import { useRouter, usePathname } from 'next/navigation';
import { useUIStore } from '@/lib/store/uiStore';
import { getTrash } from '@/lib/api/documents';

export function TrashBin() {
  const router = useRouter();
  const pathname = usePathname();
  const trashCount = useUIStore((state) => state.trashCount);
  const setTrashCount = useUIStore((state) => state.setTrashCount);

  useEffect(() => {
    getTrash().then(items => setTrashCount(items.length)).catch(() => {});
  }, [setTrashCount, pathname]);

  if (trashCount === 0) return null;

  return (
    <button
      onClick={() => router.push('/docs/trash')}
      className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-12 h-12 rounded-lg border border-border bg-background shadow-lg hover:bg-muted transition-colors"
      title={`Trash (${trashCount})`}
    >
      <Trash2 className="w-5 h-5 text-muted-foreground" />
      <span className="absolute -top-2 -right-2 min-w-5 h-5 flex items-center justify-center rounded-full bg-destructive text-destructive-foreground text-xs font-medium px-1">
        {trashCount}
      </span>
    </button>
  );
}
