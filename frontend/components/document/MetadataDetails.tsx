'use client';

import React, { useState, useEffect } from 'react';
import { Plus, X, Check, Edit2 } from 'lucide-react';
import type { Document } from '@/types';
import { updateDocumentKeywords, updateDocumentRepo } from '@/lib/api/documents';
import {
  badgeVariants,
  buttonVariants,
  inputVariants,
  linkVariants,
  scrollContainerVariants,
  tableVariants,
  textVariants,
} from '@/lib/styles/button-variants';
import { toast } from '@/lib/notifications/toast';

const KEYWORD_PRESETS = [
  'Client Facing',
  'Technical Docs',
  'Service Users',
  'Internal',
  'API Reference',
  'Architecture',
];

interface MetadataDetailsProps {
  document: Document;
  onDocumentUpdate?: (doc: Document) => void;
}

function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric'
  }) + ' ' + date.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
}

export function MetadataDetails({ document, onDocumentUpdate }: MetadataDetailsProps) {
  const [mounted, setMounted] = useState(false);
  const [showKeywordPicker, setShowKeywordPicker] = useState(false);
  const [customKeyword, setCustomKeyword] = useState('');
  const [editingRepo, setEditingRepo] = useState(false);
  const [repoUrl, setRepoUrl] = useState(document.repo_url || '');

  useEffect(() => { setMounted(true); }, []);
  useEffect(() => { setRepoUrl(document.repo_url || ''); }, [document.repo_url]);

  const keywords = document.keywords || [];
  const availablePresets = KEYWORD_PRESETS.filter(p => !keywords.includes(p));

  async function handleAddKeyword(keyword: string) {
    const trimmed = keyword.trim();
    if (!trimmed || keywords.includes(trimmed)) return;
    try {
      const updated = await updateDocumentKeywords(document.id, [...keywords, trimmed]);
      onDocumentUpdate?.(updated);
      setCustomKeyword('');
      setShowKeywordPicker(false);
    } catch {
      toast.error('Failed to update keywords');
    }
  }

  async function handleRemoveKeyword(keyword: string) {
    try {
      const updated = await updateDocumentKeywords(document.id, keywords.filter(k => k !== keyword));
      onDocumentUpdate?.(updated);
    } catch {
      toast.error('Failed to update keywords');
    }
  }

  async function handleSaveRepo() {
    try {
      const updated = await updateDocumentRepo(document.id, repoUrl.trim());
      onDocumentUpdate?.(updated);
      setEditingRepo(false);
    } catch {
      toast.error('Failed to update repository');
    }
  }

  return (
    <div className="mt-12 pt-6 border-t border-border">
      <h2 className="text-lg font-semibold mb-4">Document Metadata</h2>
      <div className={scrollContainerVariants.horizontal}>
        <table className="w-full text-sm">
        <tbody>
          {/* Keywords — editable */}
          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground align-top`}>Keywords</td>
            <td className={tableVariants.cell}>
              <div className="flex items-center gap-2 flex-wrap">
                {keywords.map(kw => (
                  <span key={kw} className={badgeVariants.keyword}>
                    {kw}
                    <button
                      onClick={() => handleRemoveKeyword(kw)}
                      className="hover:text-destructive ml-0.5"
                      title={`Remove "${kw}"`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                <div className="relative">
                  <button
                    onClick={() => setShowKeywordPicker(!showKeywordPicker)}
                    className={badgeVariants.keywordAdd}
                    title="Add keyword"
                  >
                    <Plus className="h-3 w-3" />
                    Add
                  </button>
                  {showKeywordPicker && (
                    <div className="absolute top-full left-0 mt-1 z-50 bg-background border border-border rounded-lg shadow-lg p-2 min-w-[200px]">
                      {availablePresets.map(preset => (
                        <button
                          key={preset}
                          onClick={() => handleAddKeyword(preset)}
                          className="block w-full text-left px-3 py-1.5 text-sm rounded hover:bg-muted"
                        >
                          {preset}
                        </button>
                      ))}
                      {availablePresets.length > 0 && <div className="border-t border-border my-1" />}
                      <form
                        onSubmit={(e) => { e.preventDefault(); handleAddKeyword(customKeyword); }}
                        className="flex gap-1 px-1"
                      >
                        <input
                          type="text"
                          value={customKeyword}
                          onChange={e => setCustomKeyword(e.target.value)}
                          placeholder="Custom..."
                          className={`${inputVariants.default} !py-1 !px-2 text-sm`}
                          autoFocus
                        />
                        <button type="submit" className={`${buttonVariants.primary} !px-2 !py-1 text-xs`}>
                          Add
                        </button>
                      </form>
                    </div>
                  )}
                </div>
                {keywords.length === 0 && !showKeywordPicker && (
                  <span className={`${textVariants.mutedXs} italic`}>No keywords</span>
                )}
              </div>
            </td>
          </tr>

          {/* Git Repository — editable */}
          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Git Repository</td>
            <td className={tableVariants.cell}>
              {editingRepo ? (
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    value={repoUrl}
                    onChange={e => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/org/repo"
                    className={`${inputVariants.default} !py-1 flex-1`}
                    autoFocus
                    onKeyDown={e => { if (e.key === 'Enter') handleSaveRepo(); if (e.key === 'Escape') setEditingRepo(false); }}
                  />
                  <button onClick={handleSaveRepo} className={`${buttonVariants.icon} !p-1`} title="Save">
                    <Check className="h-4 w-4" />
                  </button>
                  <button onClick={() => { setEditingRepo(false); setRepoUrl(document.repo_url || ''); }} className={`${buttonVariants.icon} !p-1`} title="Cancel">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 group">
                  {document.repo_url ? (
                    <a href={document.repo_url} target="_blank" rel="noopener noreferrer" className={linkVariants.external}>
                      {document.repo_url}
                    </a>
                  ) : (
                    <span className={`${textVariants.mutedXs} italic`}>Not set</span>
                  )}
                  <button
                    onClick={() => setEditingRepo(true)}
                    className={`${buttonVariants.icon} !p-1 opacity-0 group-hover:opacity-100 transition-opacity`}
                    title="Edit repository URL"
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </td>
          </tr>

          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Document ID</td>
            <td className={`${tableVariants.cell} font-mono text-xs`}>{document.id}</td>
          </tr>
          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Path</td>
            <td className={tableVariants.cell}>{document.path || '(root)'}</td>
          </tr>
          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Created</td>
            <td className={tableVariants.cell}>{mounted ? formatDateTime(document.created_at) : 'Loading...'}</td>
          </tr>
          <tr className={tableVariants.row}>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Last Updated</td>
            <td className={tableVariants.cell}>{mounted ? formatDateTime(document.updated_at) : 'Loading...'}</td>
          </tr>
          <tr>
            <td className={`${tableVariants.cell} font-medium text-muted-foreground`}>Generation Count</td>
            <td className={tableVariants.cell}>{document.generation_count}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>
  );
}
