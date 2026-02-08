export interface DocumentListItem {
  id: string;
  repo_name?: string;
  path: string;
  title: string;
  doc_type?: string;
  keywords: string[];
  description?: string;
  content_preview: string;
  updated_at: string;
  generation_count: number;
  version: number;
  is_indexed?: boolean;
  deleted_at?: string;
}

export interface Document extends DocumentListItem {
  content: string;
  repo_url?: string;
  created_at: string;
}

export interface Version {
  version_id: string;
  doc_id: string;
  content: string;
  content_hash: string;
  author_type: 'ai' | 'human';
  author_metadata: Record<string, any>;
  created_at: string;
}

export interface TreeNode {
  id: string;
  name: string;
  type: 'folder' | 'document';
  is_crate?: boolean;
  children?: TreeNode[];
  doc_type?: string;
  keywords?: string[];
  path?: string;
  description?: string;
  icon?: string;
}

export interface FolderGrant {
  path_prefix: string;
  role: 'admin' | 'editor' | 'viewer';
}

export interface User {
  user_id: string;
  display_name: string;
  email?: string;
  role: 'admin' | 'editor' | 'viewer';
  is_active: boolean;
  grants: FolderGrant[];
}

export interface SimilarDocument {
  id: string;
  title: string;
  path: string;
  description?: string;
  similarity_score: number;
}

export interface PersonalTreeNode {
  id: string;
  name: string;
  type: 'folder' | 'document';
  folder_id?: string;
  document_id?: string;
  ref_id?: string;
  children?: PersonalTreeNode[];
}
