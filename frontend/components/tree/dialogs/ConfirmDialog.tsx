'use client';

import React from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import { buttonVariants, dialogVariants } from '@/lib/styles/button-variants';

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
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
  if (!open) return null;

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
            <button onClick={onClose} className={buttonVariants.secondary}>
              {cancelText}
            </button>
            <button
              onClick={() => {
                onConfirm();
                onClose();
              }}
              className={confirmButtonClass}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
