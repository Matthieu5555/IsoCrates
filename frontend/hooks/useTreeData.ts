'use client';

import { useEffect, useState, useCallback } from 'react';
import { getTree, getTrash } from '@/lib/api/documents';
import { fetchApi } from '@/lib/api/client';
import type { TreeNode } from '@/types';
import { toast } from '@/lib/notifications/toast';
import { useUIStore } from '@/lib/store/uiStore';

interface GenerationJobStatus {
  status: string;
  completed_at?: string;
  error_message?: string;
}

// Max recent jobs to fetch for the status icons on crate folders.
// 50 covers typical deployments (one job per repo, ~10-50 repos).
const JOB_FETCH_LIMIT = 50;

// Backend caps the tree at 1000 documents. If we hit this count, warn the user.
const TREE_DOCUMENT_LIMIT = 1000;

export interface UseTreeDataReturn {
  tree: TreeNode[];
  loading: boolean;
  error: string | null;
  expandedNodes: Set<string>;
  generationStatus: Record<string, GenerationJobStatus>;
  loadTree: () => Promise<void>;
  toggleNode: (nodeId: string) => void;
  setExpandedNodes: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export function useTreeData(): UseTreeDataReturn {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [generationStatus, setGenerationStatus] = useState<Record<string, GenerationJobStatus>>({});

  const fetchGenerationStatus = useCallback(async (nodes: TreeNode[]) => {
    try {
      // Fetch the most recent job per repo URL (limit=50 covers typical deployments).
      // Used by DocumentTree to show status icons and error tooltips on crate folders.
      const jobs = await fetchApi<Array<{
        id: string;
        repo_url: string;
        status: string;
        completed_at?: string;
        error_message?: string;
      }>>(`/api/jobs?limit=${JOB_FETCH_LIMIT}`);

      const statusMap: Record<string, GenerationJobStatus> = {};
      for (const job of jobs) {
        if (!statusMap[job.repo_url]) {
          statusMap[job.repo_url] = {
            status: job.status,
            completed_at: job.completed_at,
            error_message: job.error_message,
          };
        }
      }
      setGenerationStatus(statusMap);
    } catch {
      // Generation jobs endpoint may not exist yet — ignore silently
    }
  }, []);

  const loadTree = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getTree();
      setTree(data);
      const firstLevel = new Set(data.map(node => node.id));
      setExpandedNodes(firstLevel);

      // Warn if tree may be truncated (backend caps at TREE_DOCUMENT_LIMIT)
      const countDocs = (nodes: TreeNode[]): number =>
        nodes.reduce((n, node) =>
          n + (node.type === 'document' ? 1 : 0) + countDocs(node.children || []), 0);
      if (countDocs(data) >= TREE_DOCUMENT_LIMIT) {
        toast.warning(
          'Tree may be incomplete',
          `Showing the first ${TREE_DOCUMENT_LIMIT} documents. Some documents may not appear in the tree.`
        );
      }

      // Fetch generation status for crate nodes
      fetchGenerationStatus(data);

      // Fetch trash count for floating indicator
      getTrash().then(items => useUIStore.getState().setTrashCount(items.length)).catch(() => {});
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load tree';
      setError(message);
      toast.error('Failed to load tree', message);
    } finally {
      setLoading(false);
    }
  }, [fetchGenerationStatus]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const toggleNode = useCallback((nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  return {
    tree,
    loading,
    error,
    expandedNodes,
    generationStatus,
    loadTree,
    toggleNode,
    setExpandedNodes,
  };
}
