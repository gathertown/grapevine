import { useState, FC, memo } from 'react';
import {
  Flex,
  Text,
  Button,
  Input,
  Modal,
  Icon,
  Badge,
  Box,
} from '@gathertown/gather-design-system';
import { type APIKeyInfo } from '../api/api-keys';
import { SectionHeader } from './shared/SectionHeader';
import { SectionContainer } from './shared/SectionContainer';
import { CopyButton } from './shared/CopyButton';
import { useApiKeys } from '../contexts/ApiKeysContext';
import { DOCS_URL } from '../constants';

const ApiKeysPage: FC = memo(() => {
  const { keys, loading, error, createKey, deleteKey, refreshKeys } = useApiKeys();

  // Create modal state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  // Delete modal state
  const [keyToDelete, setKeyToDelete] = useState<APIKeyInfo | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) {
      setCreateError('Please enter a name for the API key');
      return;
    }

    try {
      setCreating(true);
      setCreateError(null);
      const response = await createKey(newKeyName.trim());

      // Show the created key
      setCreatedKey(response.apiKey);

      // Reset form
      setNewKeyName('');
    } catch (err) {
      console.error('Failed to create API key:', err);
      setCreateError('Failed to create API key. Please try again.');
    } finally {
      setCreating(false);
    }
  };

  const handleCloseCreateModal = () => {
    setIsCreateModalOpen(false);
    setNewKeyName('');
    setCreateError(null);
    setCreatedKey(null);
  };

  const handleDeleteKey = async () => {
    if (!keyToDelete) return;

    try {
      setDeleting(true);
      setDeleteError(null);
      await deleteKey(keyToDelete.id);

      // Close modal
      setKeyToDelete(null);
    } catch (err) {
      console.error('Failed to delete API key:', err);
      setDeleteError('Failed to delete API key. Please try again.');
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <Flex width="100%" direction="column" gap={32}>
      {/* Header Section */}
      <Flex direction="column">
        <SectionHeader title="API Keys" />
        <SectionContainer>
          <Flex direction="row" align="center" justify="space-between">
            <Flex direction="column" gap={8}>
              <Text fontSize="md" fontWeight="semibold">
                API Access
              </Text>
              <Text fontSize="sm" color="tertiary">
                Generate API keys to integrate Grapevine into your applications. Each key provides
                access to company-wide data only (no access to private data).
                {DOCS_URL && (
                  <>
                    {' '}
                    <a
                      href={`${DOCS_URL}/getting-started/authentication`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ textDecoration: 'underline' }}
                    >
                      Learn more →
                    </a>
                  </>
                )}
              </Text>
            </Flex>
            <Button onClick={() => setIsCreateModalOpen(true)} kind="primary">
              Create API Key
            </Button>
          </Flex>
        </SectionContainer>
      </Flex>

      {/* API Keys List */}
      <Flex direction="column">
        <SectionHeader title="Your API Keys" />
        {loading ? (
          <Text color="tertiary">Loading API keys...</Text>
        ) : error ? (
          <Flex direction="column" gap={16}>
            <Text color="dangerPrimary">{error}</Text>
            <Button onClick={refreshKeys} kind="secondary">
              Retry
            </Button>
          </Flex>
        ) : keys.length === 0 ? (
          <SectionContainer>
            <Flex direction="column" gap={8} align="center" py={32}>
              <Icon name="codeInline" size="lg" color="tertiary" />
              <Text color="tertiary">No API keys yet</Text>
            </Flex>
          </SectionContainer>
        ) : (
          <Flex direction="column" gap={16}>
            {keys.map((key) => (
              <Flex
                key={key.id}
                direction="row"
                align="center"
                justify="space-between"
                p={16}
                borderWidth={1}
                borderStyle="solid"
                borderColor="tertiary"
                borderRadius={8}
              >
                <Flex direction="column" gap={4} flex={1}>
                  <Flex direction="row" align="center" gap={8}>
                    <Text fontSize="md" fontWeight="semibold">
                      {key.name}
                    </Text>
                    <Badge color="gray" text={`${key.prefix}...`} size="sm" />
                  </Flex>
                  <Flex direction="row" gap={16}>
                    <Text fontSize="xs" color="tertiary">
                      Created {formatDate(key.createdAt)}
                    </Text>
                    {key.lastUsedAt && (
                      <Text fontSize="xs" color="tertiary">
                        Last used {formatDate(key.lastUsedAt)}
                      </Text>
                    )}
                  </Flex>
                </Flex>
                <Button onClick={() => setKeyToDelete(key)} kind="dangerSecondary" size="sm">
                  Delete
                </Button>
              </Flex>
            ))}
          </Flex>
        )}
      </Flex>

      {/* Create Key Modal */}
      <Modal open={isCreateModalOpen} onOpenChange={() => !creating && handleCloseCreateModal()}>
        <Modal.Content style={{ width: '500px' }} variant="auto">
          <Modal.Header title={createdKey ? 'API Key Created' : 'Create API Key'} />
          <Modal.Body>
            <Flex direction="column" gap={24}>
              {createdKey ? (
                <>
                  <Flex direction="column" gap={8}>
                    <Text fontSize="sm" fontWeight="semibold">
                      Save your API key
                    </Text>
                    <Text fontSize="sm" color="tertiary">
                      This is the only time you'll see the full key. Copy it now and store it
                      securely.
                    </Text>
                  </Flex>
                  <Flex direction="column" gap={8}>
                    <Flex
                      direction="row"
                      align="center"
                      gap={8}
                      p={12}
                      backgroundColor="tertiary"
                      borderRadius={8}
                    >
                      <Box
                        style={{
                          flex: 1,
                          wordBreak: 'break-all',
                          fontFamily: 'monospace',
                          fontSize: '14px',
                        }}
                      >
                        {createdKey}
                      </Box>
                      <CopyButton textToCopy={createdKey} size="sm" />
                    </Flex>
                  </Flex>
                  <Flex direction="row" justify="flex-end">
                    <Button onClick={handleCloseCreateModal} kind="primary">
                      Done
                    </Button>
                  </Flex>
                </>
              ) : (
                <>
                  <Flex direction="column" gap={8}>
                    <Text fontSize="sm" fontWeight="semibold">
                      Name
                    </Text>
                    <Input
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="e.g., Production API Key"
                      disabled={creating}
                    />
                  </Flex>
                  {createError && (
                    <Text fontSize="sm" color="dangerPrimary">
                      {createError}
                    </Text>
                  )}
                  <Flex direction="row" justify="flex-end" gap={8}>
                    <Button onClick={handleCloseCreateModal} kind="secondary" disabled={creating}>
                      Cancel
                    </Button>
                    <Button onClick={handleCreateKey} kind="primary" disabled={creating}>
                      {creating ? 'Creating...' : 'Create'}
                    </Button>
                  </Flex>
                </>
              )}
            </Flex>
          </Modal.Body>
        </Modal.Content>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal open={!!keyToDelete} onOpenChange={() => !deleting && setKeyToDelete(null)}>
        <Modal.Content style={{ width: '400px' }} variant="auto">
          <Modal.Header title="Delete API Key" />
          <Modal.Body>
            <Flex direction="column" gap={24}>
              <Text fontSize="sm" color="secondary">
                Are you sure you want to delete{' '}
                <Text as="span" fontWeight="semibold">
                  {keyToDelete?.name}
                </Text>
                ? This action cannot be undone and any applications using this key will stop
                working.
              </Text>
              {deleteError && (
                <Text fontSize="sm" color="dangerPrimary">
                  {deleteError}
                </Text>
              )}
              <Flex direction="row" justify="flex-end" gap={8}>
                <Button onClick={() => setKeyToDelete(null)} kind="secondary" disabled={deleting}>
                  Cancel
                </Button>
                <Button onClick={handleDeleteKey} kind="danger" disabled={deleting}>
                  {deleting ? 'Deleting...' : 'Delete Key'}
                </Button>
              </Flex>
            </Flex>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </Flex>
  );
});

ApiKeysPage.displayName = 'ApiKeysPage';

export { ApiKeysPage };
