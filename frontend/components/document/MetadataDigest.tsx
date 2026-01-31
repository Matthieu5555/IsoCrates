'use client';

import React, { useState, useEffect } from 'react';
import { Edit, Trash2 } from 'lucide-react';
import type { Document } from '@/types';
import { buttonVariants } from '@/lib/styles/button-variants';

interface MetadataDigestProps {
  document: Document;
  onEdit?: () => void;
  onDelete?: () => void;
  isEditing?: boolean;
  latestAuthor?: string;
  latestDate?: string;
}

export function MetadataDigest({
  document,
  onEdit,
  onDelete,
  isEditing = false,
  latestAuthor = 'ai',
  latestDate,
}: MetadataDigestProps) {
  const [mounted, setMounted] = useState(false);
  const [formattedDate, setFormattedDate] = useState<string>('');
  const [formattedDateTime, setFormattedDateTime] = useState<string>('');

  useEffect(() => {
    setMounted(true);
    const date = new Date(document.updated_at);
    setFormattedDate(date.toLocaleDateString('en-GB', {
      day: '2-digit', month: '2-digit', year: 'numeric'
    }));
    const dateToFormat = latestDate || document.updated_at;
    const dateTime = new Date(dateToFormat);
    setFormattedDateTime(
      dateTime.toLocaleDateString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric'
      }) + ' at ' + dateTime.toLocaleTimeString('en-GB', {
        hour: '2-digit', minute: '2-digit', hour12: false
      })
    );
  }, [document.updated_at, latestDate]);

  const authorName = latestAuthor === 'human' ? 'admin' : 'IsoCrates';

  if (!mounted) {
    return (
      <div className="border-b border-border pb-4 mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>Updated: ...</span>
            <span>Gen #{document.generation_count}</span>
          </div>
        </div>
        <div className="text-sm text-muted-foreground italic">Loading...</div>
      </div>
    );
  }

  return (
    <div className="border-b border-border pb-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>Updated: {formattedDate || '...'}</span>
          <span>&bull;</span>
          <span>Gen #{document.generation_count}</span>
        </div>

        {!isEditing && (
          <div className="flex items-center gap-3">
            {onEdit && (
              <button onClick={onEdit} className={`${buttonVariants.secondary} flex items-center gap-2`}>
                <Edit className="h-4 w-4" />
                Edit
              </button>
            )}
            {onDelete && (
              <button onClick={onDelete} className={`${buttonVariants.danger} flex items-center gap-2`}>
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            )}
          </div>
        )}

        {isEditing && (
          <span className="px-3 py-1.5 text-sm font-medium text-muted-foreground">
            Editing...
          </span>
        )}
      </div>

      <div className="text-sm text-muted-foreground italic">
        Documentation written by {authorName} on {formattedDateTime || '...'}
      </div>
    </div>
  );
}
