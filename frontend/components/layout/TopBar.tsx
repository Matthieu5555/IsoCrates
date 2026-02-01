'use client';

import React, { useState } from 'react';
import { Menu, Search, Settings, GitBranch } from 'lucide-react';
import Link from 'next/link';
import { useUIStore } from '@/lib/store/uiStore';
import { useSearch } from '@/hooks/useSearch';
import { SettingsDialog } from '../settings/SettingsDialog';
import { buttonVariants, kbdVariants } from '@/lib/styles/button-variants';

export function TopBar() {
  const { toggleSidebar } = useUIStore();
  const { setOpen: setSearchOpen } = useSearch();
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-14 items-center px-4 md:px-6 gap-4">
          {/* Left section: Sidebar toggle + Logo */}
          <div className="flex items-center gap-3">
            <button
              onClick={toggleSidebar}
              className={buttonVariants.icon}
              aria-label="Toggle sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>

            <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <h1 className="text-sm font-semibold">IsoCrates  |  Homepage</h1>
            </Link>
          </div>

          {/* Right section: Graph + Search + Settings */}
          <div className="flex items-center gap-3 ml-auto">
            <Link
              href="/graph"
              className={buttonVariants.icon}
              aria-label="Dependency Graph"
              title="Dependency Graph"
            >
              <GitBranch className="h-5 w-5" />
            </Link>

            <button
              onClick={() => setSearchOpen(true)}
              className={buttonVariants.commandTrigger}
              aria-label="Search documents"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:inline">Search...</span>
              <kbd className={`hidden sm:${kbdVariants.trigger}`}>
                <span className="text-xs">⌘K</span>
              </kbd>
            </button>

            <button
              onClick={() => setSettingsOpen(true)}
              className={buttonVariants.icon}
              aria-label="Settings"
            >
              <Settings className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </>
  );
}
