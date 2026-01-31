'use client';

import React from 'react';
import { useTreeStore } from '@/lib/store/treeStore';

export function TreeTabs() {
  const { activeTab, setActiveTab } = useTreeStore();

  return (
    <div className="border-t border-border flex">
      <button
        onClick={() => setActiveTab('org')}
        className={`flex-1 px-3 py-2.5 text-xs font-medium transition-colors ${
          activeTab === 'org'
            ? 'bg-accent text-foreground'
            : 'text-muted-foreground hover:bg-muted/50'
        }`}
      >
        Org Tree
      </button>
      <button
        onClick={() => setActiveTab('personal')}
        className={`flex-1 px-3 py-2.5 text-xs font-medium transition-colors border-l border-border ${
          activeTab === 'personal'
            ? 'bg-accent text-foreground'
            : 'text-muted-foreground hover:bg-muted/50'
        }`}
      >
        Personal Tree
      </button>
    </div>
  );
}
