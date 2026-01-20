import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

// ============================================================================
// Types
// ============================================================================

// Simplified field types aligned with Glean's API
export type CustomFieldType = 'text' | 'date' | 'number';

export interface CustomFieldDefinition {
  name: string;
  type: CustomFieldType;
  required?: boolean;
  description?: string;
}

export interface CustomFieldsSchema {
  fields: CustomFieldDefinition[];
  version: number;
}

export enum CustomDocumentTypeState {
  ENABLED = 'enabled',
  DISABLED = 'disabled',
  DELETED = 'deleted',
}

export interface CustomDocumentType {
  id: string;
  display_name: string;
  slug: string;
  description: string | null;
  custom_fields: CustomFieldsSchema;
  state: CustomDocumentTypeState;
  ingest_endpoint: string;
  created_at: string;
  updated_at: string;
}

export interface CreateCustomDocumentTypeParams {
  display_name: string;
  description?: string;
  custom_fields?: CustomFieldsSchema;
}

export interface UpdateCustomDocumentTypeParams {
  display_name?: string;
  description?: string | null;
  custom_fields?: CustomFieldsSchema;
  state?: CustomDocumentTypeState;
}

// ============================================================================
// Query Keys
// ============================================================================

export interface CustomDocumentTypeStats {
  documentCount: number;
  artifactCount: number;
}

export interface DeleteCustomDocumentTypeResult {
  success: boolean;
  deletedId: string;
  documentsDeleted: number;
  artifactsDeleted: number;
}

export const customDataQueryKeys = {
  all: ['custom-data'] as const,
  types: () => [...customDataQueryKeys.all, 'types'] as const,
  type: (id: string) => [...customDataQueryKeys.types(), id] as const,
  typeStats: (id: string) => [...customDataQueryKeys.type(id), 'stats'] as const,
};

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch all custom document types
 */
export const useCustomDocumentTypes = () => {
  return useQuery<{ documentTypes: CustomDocumentType[] }>({
    queryKey: customDataQueryKeys.types(),
    queryFn: () => apiClient.get<{ documentTypes: CustomDocumentType[] }>('/api/custom-data/types'),
  });
};

/**
 * Fetch a single custom document type by ID
 */
export const useCustomDocumentType = (id: string) => {
  return useQuery<{ documentType: CustomDocumentType }>({
    queryKey: customDataQueryKeys.type(id),
    queryFn: () =>
      apiClient.get<{ documentType: CustomDocumentType }>(`/api/custom-data/types/${id}`),
    enabled: !!id,
  });
};

/**
 * Fetch stats for a custom document type (document count, etc.)
 */
export const useCustomDocumentTypeStats = (id: string) => {
  return useQuery<CustomDocumentTypeStats>({
    queryKey: customDataQueryKeys.typeStats(id),
    queryFn: () => apiClient.get<CustomDocumentTypeStats>(`/api/custom-data/types/${id}/stats`),
    enabled: !!id,
  });
};

/**
 * Create a new custom document type
 */
export const useCreateCustomDocumentType = () => {
  const queryClient = useQueryClient();

  return useMutation<{ documentType: CustomDocumentType }, Error, CreateCustomDocumentTypeParams>({
    mutationFn: (params) =>
      apiClient.post<{ documentType: CustomDocumentType }>('/api/custom-data/types', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: customDataQueryKeys.types() });
    },
  });
};

/**
 * Update an existing custom document type
 */
export const useUpdateCustomDocumentType = () => {
  const queryClient = useQueryClient();

  return useMutation<
    { documentType: CustomDocumentType },
    Error,
    { id: string; params: UpdateCustomDocumentTypeParams }
  >({
    mutationFn: ({ id, params }) =>
      apiClient.put<{ documentType: CustomDocumentType }>(`/api/custom-data/types/${id}`, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: customDataQueryKeys.types() });
    },
  });
};

/**
 * Delete a custom document type (soft delete) and its documents/artifacts
 */
export const useDeleteCustomDocumentType = () => {
  const queryClient = useQueryClient();

  return useMutation<DeleteCustomDocumentTypeResult, Error, string>({
    mutationFn: (id) =>
      apiClient.delete<DeleteCustomDocumentTypeResult>(`/api/custom-data/types/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: customDataQueryKeys.types() });
    },
  });
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Generate a slug from a display name
 * Matches the backend implementation
 */
export function generateSlug(displayName: string): string {
  return displayName
    .toLowerCase()
    .replace(/\s+/g, '-') // spaces → hyphens
    .replace(/[^a-z0-9-]/g, '') // remove special chars
    .replace(/-+/g, '-') // collapse multiple hyphens
    .replace(/^-|-$/g, ''); // trim hyphens
}

/**
 * Get human-readable label for a field type
 */
export function getFieldTypeLabel(type: CustomFieldType): string {
  const labels: Record<CustomFieldType, string> = {
    text: 'Text',
    date: 'Date',
    number: 'Number',
  };
  return labels[type];
}
