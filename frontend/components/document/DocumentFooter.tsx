'use client';

import React, { useState, useEffect } from 'react';
import type { Document } from '@/types';

interface DocumentFooterProps {
  document: Document;
  latestAuthor?: string;
  latestDate?: string;
}

export function DocumentFooter({ document, latestAuthor = 'ai', latestDate }: DocumentFooterProps) {
  const [formattedDate, setFormattedDate] = useState<string>('');

  useEffect(() => {
    const dateToFormat = latestDate || document.updated_at;
    const date = new Date(dateToFormat);
    setFormattedDate(date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    }) + ' at ' + date.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }));
  }, [latestDate, document.updated_at]);

  const authorName = latestAuthor === 'human' ? 'admin' : 'IsoCrates';

  return (
    <div className="mt-8 pt-4 border-t border-border text-sm text-muted-foreground italic">
      Documentation written by {authorName} on {formattedDate || '...'}
    </div>
  );
}
