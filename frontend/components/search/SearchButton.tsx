'use client';

import React from 'react';
import { Search } from 'lucide-react';
import { buttonVariants, kbdVariants } from '@/lib/styles/button-variants';

interface SearchButtonProps {
  onClick: () => void;
}

export function SearchButton({ onClick }: SearchButtonProps) {
  return (
    <button
      onClick={onClick}
      className={buttonVariants.commandTrigger}
    >
      <Search className="h-4 w-4" />
      <span>Search documentation...</span>
      <kbd className={`hidden sm:inline-flex ${kbdVariants.trigger}`}>
        <span className="text-xs">⌘</span>K
      </kbd>
    </button>
  );
}
