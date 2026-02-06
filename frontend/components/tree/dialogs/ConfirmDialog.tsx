'use client';

import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X, Loader2 } from 'lucide-react';
import { buttonVariants, dialogVariants } from '@/lib/styles/button-variants';

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'info';
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger',
}: ConfirmDialogProps) {
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  async function handleConfirm() {
    setLoading(true);
    try {
      await onConfirm();
      onClose();
    } catch {
      // Error already handled by onConfirm, just close
      onClose();
    } finally {
      setLoading(false);
    }
  }

  const confirmButtonClass = variant === 'danger' ? buttonVariants.danger : buttonVariants.primary;

  return createPortal(
    <div className={dialogVariants.overlay} onClick={onClose}>
      <div className={`${dialogVariants.container} max-w-md`} onClick={(e) => e.stopPropagation()}>
        <div className={dialogVariants.content}>
          {/* Header */}
          <div className={dialogVariants.header}>
            <div className="flex items-center gap-2">
              {variant === 'danger' && <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />}
              {variant === 'warning' && <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />}
              <h2 className={dialogVariants.title}>{title}</h2>
            </div>
            <button onClick={onClose} className={buttonVariants.icon}>
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className={dialogVariants.body}>
            <p className="text-sm text-foreground">{message}</p>
          </div>

          {/* Footer */}
          <div className={dialogVariants.footer}>
            <button onClick={onClose} disabled={loading} className={buttonVariants.secondary}>
              {cancelText}
            </button>
            <button
              onClick={handleConfirm}
              disabled={loading}
              className={confirmButtonClass}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </span>
              ) : (
                confirmText
              )}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
