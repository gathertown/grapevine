import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
  memo,
} from 'react';
import { apiKeysApi, type APIKeyInfo } from '../api/api-keys';
import { useAuth } from '../hooks/useAuth';

export interface ApiKeysContextType {
  keys: APIKeyInfo[];
  loading: boolean;
  error: string | null;
  isInitialized: boolean;
  createKey: (name: string) => Promise<{ apiKey: string; keyInfo: APIKeyInfo }>;
  deleteKey: (keyId: string) => Promise<void>;
  refreshKeys: () => Promise<void>;
}

const ApiKeysContext = createContext<ApiKeysContextType | null>(null);

interface ApiKeysProviderProps {
  children: ReactNode;
}

export const ApiKeysProvider = memo(({ children }: ApiKeysProviderProps) => {
  const { isProvisioningComplete } = useAuth();
  const [keys, setKeys] = useState<APIKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiKeysApi.listKeys();
      setKeys(response.keys);
      setIsInitialized(true);
    } catch (err) {
      console.error('Failed to load API keys:', err);
      setError('Failed to load API keys. Please try again.');
      setKeys([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load API keys on mount when provisioning is complete
  useEffect(() => {
    if (isProvisioningComplete) {
      loadKeys();
    }
  }, [isProvisioningComplete, loadKeys]);

  const createKey = useCallback(async (name: string) => {
    if (!name.trim()) {
      throw new Error('Please enter a name for the API key');
    }

    const response = await apiKeysApi.createKey(name.trim());

    // Add to list
    setKeys((prevKeys) => [response.keyInfo, ...prevKeys]);

    return response;
  }, []);

  const deleteKey = useCallback(async (keyId: string) => {
    await apiKeysApi.deleteKey(keyId);

    // Remove from list
    setKeys((prevKeys) => prevKeys.filter((k) => k.id !== keyId));
  }, []);

  const refreshKeys = useCallback(async () => {
    await loadKeys();
  }, [loadKeys]);

  const value: ApiKeysContextType = {
    keys,
    loading,
    error,
    isInitialized,
    createKey,
    deleteKey,
    refreshKeys,
  };

  return <ApiKeysContext.Provider value={value}>{children}</ApiKeysContext.Provider>;
});

ApiKeysProvider.displayName = 'ApiKeysProvider';

export const useApiKeys = (): ApiKeysContextType => {
  const context = useContext(ApiKeysContext);
  if (!context) {
    throw new Error('useApiKeys must be used within an ApiKeysProvider');
  }
  return context;
};
