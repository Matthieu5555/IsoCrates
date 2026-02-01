'use client';

import React, { useEffect, useState } from 'react';
import { toast, type Toast } from '@/lib/notifications/toast';
import { X, CheckCircle2, AlertCircle, AlertTriangle, Info } from 'lucide-react';

const ICON_MAP = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
} as const;

const COLOR_MAP = {
  success: 'border-green-500/30 bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-200',
  error: 'border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200',
  warning: 'border-yellow-500/30 bg-yellow-50 dark:bg-yellow-950/30 text-yellow-800 dark:text-yellow-200',
  info: 'border-blue-500/30 bg-blue-50 dark:bg-blue-950/30 text-blue-800 dark:text-blue-200',
} as const;

/**
 * Renders toast notifications from the global ToastManager.
 *
 * Mount once at the root layout. Subscribes to the singleton toast manager
 * and displays notifications as a fixed overlay in the bottom-right corner.
 */
export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    setToasts(toast.getToasts());
    return toast.subscribe(setToasts);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => {
        const Icon = ICON_MAP[t.type];
        return (
          <div
            key={t.id}
            className={`flex items-start gap-3 rounded-md border p-3 shadow-lg backdrop-blur-sm animate-in slide-in-from-right-5 fade-in duration-200 ${COLOR_MAP[t.type]}`}
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{t.title}</p>
              {t.message && (
                <p className="text-xs mt-0.5 opacity-80">{t.message}</p>
              )}
            </div>
            <button
              onClick={() => toast.remove(t.id)}
              className="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
