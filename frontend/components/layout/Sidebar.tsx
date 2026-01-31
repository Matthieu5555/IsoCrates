'use client';

import React from 'react';
import { DocumentTree } from '../tree/DocumentTree';
import { PersonalTree } from '../tree/PersonalTree';
import { TreeTabs } from '../tree/TreeTabs';
import { SearchCommand } from '../search/SearchCommand';
import { useSearch } from '@/hooks/useSearch';
import { useUIStore } from '@/lib/store/uiStore';
import { useTreeStore } from '@/lib/store/treeStore';

export function Sidebar() {
  const { open, setOpen } = useSearch();
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed);
  const activeTab = useTreeStore((state) => state.activeTab);

  if (sidebarCollapsed) {
    return (
      <>
        <SearchCommand open={open} onOpenChange={setOpen} />
      </>
    );
  }

  return (
    <>
      <div className="h-full flex flex-col">
        <div className="flex-1 overflow-hidden">
          {activeTab === 'org' ? <DocumentTree /> : <PersonalTree />}
        </div>
        <TreeTabs />
      </div>

      <SearchCommand open={open} onOpenChange={setOpen} />
    </>
  );
}
