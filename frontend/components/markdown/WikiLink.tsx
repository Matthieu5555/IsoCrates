'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { resolveWikilink } from '@/lib/api/documents';
import { linkVariants } from '@/lib/styles/button-variants';
import { getApiErrorMessage } from '@/lib/api/client';
import { toast } from '@/lib/notifications/toast';

interface WikiLinkProps {
  target: string;
  children: React.ReactNode;
  /** Pre-computed broken state from the broken-links API. */
  broken?: boolean;
}

export function WikiLink({ target, children, broken }: WikiLinkProps) {
  const router = useRouter();
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();

    if (isResolving) return;

    setIsResolving(true);
    try {
      const docId = await resolveWikilink(target);
      if (docId) {
        router.push(`/docs/${docId}`);
        setError(null);
      } else {
        const errorMsg = `Document not found: ${target}`;
        setError(errorMsg);
        toast.warning('Link Not Found', `Could not find document: ${target}`);
      }
    } catch (error) {
      console.error('Error resolving wikilink:', error);
      const message = getApiErrorMessage(error);
      setError(message);
      toast.error('Link Error', message);
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <a
      href="#"
      onClick={handleClick}
      className={`${linkVariants.default} cursor-pointer ${
        error || broken ? 'text-red-500 line-through decoration-red-500/50' : ''
      }`}
      title={error || broken ? `Broken link: ${target}` : `Link to: ${target}`}
    >
      {children}
      {isResolving && ' ⏳'}
      {error && ' ⚠️'}
    </a>
  );
}
