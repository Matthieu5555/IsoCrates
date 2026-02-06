'use client';

import { useEffect, useState, useCallback } from 'react';
import { getPersonalTree } from '@/lib/api/personal';
import type { PersonalTreeNode } from '@/types';
import { toast } from '@/lib/notifications/toast';

export interface UsePersonalTreeDataReturn {
  tree: PersonalTreeNode[];
  loading: boolean;
  error: string | null;
  expandedNodes: Set<string>;
  loadTree: () => Promise<void>;
  toggleNode: (nodeId: string) => void;
  setExpandedNodes: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export function usePersonalTreeData(): UsePersonalTreeDataReturn {
  const [tree, setTree] = useState<PersonalTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const loadTree = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPersonalTree();
      setTree(data);
      const firstLevel = new Set(data.map(node => node.id));
      setExpandedNodes(firstLevel);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load personal tree';
      setError(message);
      toast.error('Failed to load personal tree', message);
    } finally {
      setLoading(false);
    }
  }, []);

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
    loadTree,
    toggleNode,
    setExpandedNodes,
  };
}
