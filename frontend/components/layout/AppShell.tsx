'use client';

import React, { useRef, useState, useEffect } from 'react';
import { useUIStore } from '@/lib/store/uiStore';
import { useSearchStore } from '@/lib/store/searchStore';
import { TopBar } from './TopBar';
import { TrashBin } from './TrashBin';

interface AppShellProps {
  sidebar: React.ReactNode;
  children: React.ReactNode;
}

export function AppShell({ sidebar, children }: AppShellProps) {
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed);
  const sidebarWidth = useUIStore((state) => state.sidebarWidth);
  const setSidebarWidth = useUIStore((state) => state.setSidebarWidth);
  const [isResizing, setIsResizing] = useState(false);

  // Global keyboard shortcuts for search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // CMD+K (Mac) or Ctrl+K (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        useSearchStore.getState().toggle();
      }

      // Escape to close
      if (e.key === 'Escape') {
        useSearchStore.getState().setOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  React.useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      setSidebarWidth(e.clientX);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, setSidebarWidth]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Top Bar */}
      <TopBar />

      {/* Main layout with sidebar and content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside
          className="border-r border-border bg-muted/20 overflow-y-auto relative p-3"
          style={{
            width: sidebarCollapsed ? 0 : `${sidebarWidth}px`,
            transition: isResizing ? 'none' : 'width 0.3s',
          }}
        >
          {sidebar}

          {/* Resize handle */}
          {!sidebarCollapsed && (
            <div
              onMouseDown={handleMouseDown}
              className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 transition-colors group"
            >
              <div className="absolute right-0 top-0 bottom-0 w-1.5 bg-transparent group-hover:bg-primary/50" />
            </div>
          )}
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 relative">
          {children}
        </main>
      </div>

      <TrashBin />
    </div>
  );
}
