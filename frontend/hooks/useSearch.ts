'use client';

import { useSearchStore } from '@/lib/store/searchStore';

export function useSearch() {
  const open = useSearchStore((state) => state.open);
  const setOpen = useSearchStore((state) => state.setOpen);

  return { open, setOpen };
}
