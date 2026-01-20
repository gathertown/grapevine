import { memo, useEffect, useState } from 'react';
import type { FC } from 'react';
import {
  Flex,
  Text,
  Box,
  Button,
  Loader,
  Input,
  Modal,
  ToggleSwitch,
} from '@gathertown/gather-design-system';
import { apiClient } from '../api/client';
import { SectionContainer, SectionHeader } from './shared';
import { CopyButton } from './shared/CopyButton';
import type {
  WebhookSubscription,
  CreateWebhookRequest,
  UpdateWebhookRequest,
  WebhookSubscriptionsResponse,
} from '../types';
import { DOCS_URL } from '../constants';

interface CreateWebhookModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (webhook: WebhookSubscription) => void;
}

const CreateWebhookModal: FC<CreateWebhookModalProps> = memo(({ isOpen, onClose, onSuccess }) => {
  const [url, setUrl] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdWebhook, setCreatedWebhook] = useState<WebhookSubscription | null>(null);

  const handleCreate = async () => {
    if (!url.trim()) {
      setError('URL is required');
      return;
    }

    if (!url.startsWith('https://')) {
      setError('URL must start with https://');
      return;
    }

    try {
      setIsCreating(true);
      setError(null);
      const request: CreateWebhookRequest = { url: url.trim() };
      const webhook: WebhookSubscription = await apiClient.post<WebhookSubscription>(
        '/api/webhook-subscriptions',
        request
      );
      setCreatedWebhook(webhook);
      onSuccess(webhook);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create webhook');
    } finally {
      setIsCreating(false);
    }
  };

  const handleClose = () => {
    setUrl('');
    setError(null);
    setCreatedWebhook(null);
    onClose();
  };

  return (
    <Modal open={isOpen} onOpenChange={handleClose}>
      <Modal.Content style={{ width: '500px' }} variant="auto">
        <Modal.Header title={createdWebhook ? 'Webhook Created' : 'Create Webhook Subscription'} />
        <Modal.Body>
          <Flex direction="column" gap={16}>
            {createdWebhook ? (
              <Flex direction="column" gap={16}>
                <Text fontSize="md" color="primary">
                  Webhook subscription created successfully!
                </Text>

                <Box p={12} backgroundColor="secondary" borderRadius={6}>
                  <Flex direction="column" gap={8}>
                    <Text fontSize="sm" fontWeight="medium" color="primary">
                      Webhook URL:
                    </Text>
                    <Text fontSize="sm" color="tertiary">
                      {createdWebhook.url}
                    </Text>
                  </Flex>
                </Box>

                {createdWebhook.secret && (
                  <Box p={12} backgroundColor="accentSecondary" borderRadius={6}>
                    <Flex direction="column" gap={8}>
                      <Text fontSize="sm" fontWeight="medium" color="primary">
                        Signing Secret (save this - it won't be shown again):
                      </Text>
                      <Flex align="center" gap={8}>
                        <Text fontSize="sm" color="primary">
                          {createdWebhook.secret}
                        </Text>
                        <CopyButton textToCopy={createdWebhook.secret} />
                      </Flex>
                    </Flex>
                  </Box>
                )}

                <Flex justify="flex-end">
                  <Button onClick={handleClose} kind="primary">
                    Done
                  </Button>
                </Flex>
              </Flex>
            ) : (
              <>
                <Flex direction="column" gap={8}>
                  <Text fontSize="sm" fontWeight="medium" color="primary">
                    Webhook URL
                  </Text>
                  <Input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://api.example.com/webhooks/grapevine"
                    disabled={isCreating}
                  />
                  {error && (
                    <Text fontSize="sm" color="dangerPrimary">
                      {error}
                    </Text>
                  )}
                </Flex>

                <Flex justify="flex-end" gap={12}>
                  <Button onClick={handleClose} kind="secondary" disabled={isCreating}>
                    Cancel
                  </Button>
                  <Button onClick={handleCreate} kind="primary" disabled={isCreating}>
                    {isCreating ? 'Creating...' : 'Create Webhook'}
                  </Button>
                </Flex>
              </>
            )}
          </Flex>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
});

CreateWebhookModal.displayName = 'CreateWebhookModal';

interface DeleteWebhookModalProps {
  webhook: WebhookSubscription | null;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const DeleteWebhookModal: FC<DeleteWebhookModalProps> = memo(
  ({ webhook, isOpen, onClose, onSuccess }) => {
    const [isDeleting, setIsDeleting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleDelete = async () => {
      if (!webhook) return;

      try {
        setIsDeleting(true);
        setError(null);
        await apiClient.delete(`/api/webhook-subscriptions/${webhook.id}`);
        onSuccess();
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete webhook');
      } finally {
        setIsDeleting(false);
      }
    };

    const handleClose = () => {
      setError(null);
      onClose();
    };

    if (!webhook) return null;

    return (
      <Modal open={isOpen} onOpenChange={handleClose}>
        <Modal.Content style={{ width: '500px' }} variant="auto">
          <Modal.Header title="Delete Webhook Subscription" />
          <Modal.Body>
            <Flex direction="column" gap={16}>
              <Text fontSize="md" color="primary">
                Are you sure you want to delete this webhook subscription?
              </Text>

              <Box p={12} backgroundColor="secondary" borderRadius={6}>
                <Text fontSize="sm" color="tertiary">
                  {webhook.url}
                </Text>
              </Box>

              <Text fontSize="sm" color="tertiary">
                This action cannot be undone.
              </Text>

              {error && (
                <Text fontSize="sm" color="dangerPrimary">
                  {error}
                </Text>
              )}

              <Flex justify="flex-end" gap={12}>
                <Button onClick={handleClose} kind="secondary" disabled={isDeleting}>
                  Cancel
                </Button>
                <Button onClick={handleDelete} kind="danger" disabled={isDeleting}>
                  {isDeleting ? 'Deleting...' : 'Delete Webhook'}
                </Button>
              </Flex>
            </Flex>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    );
  }
);

DeleteWebhookModal.displayName = 'DeleteWebhookModal';

interface WebhookCardProps {
  webhook: WebhookSubscription;
  onToggleActive: (webhook: WebhookSubscription, active: boolean) => void;
  onDelete: (webhook: WebhookSubscription) => void;
}

const WebhookCard: FC<WebhookCardProps> = memo(({ webhook, onToggleActive, onDelete }) => {
  return (
    <Box
      p={16}
      borderRadius={8}
      borderWidth={1}
      borderStyle="solid"
      borderColor="tertiary"
      backgroundColor="primary"
    >
      <Flex direction="column" gap={12}>
        <Flex justify="space-between" align="flex-start" gap={12}>
          <Flex direction="column" gap={4} flexGrow={1}>
            <Text fontSize="md" fontWeight="medium" color="primary">
              {webhook.url}
            </Text>
            <Text fontSize="xs" color="tertiary">
              Created: {new Date(webhook.created_at).toLocaleDateString()}
            </Text>
          </Flex>

          <Flex gap={12} align="center">
            <Flex align="center" gap={8}>
              <Text fontSize="sm" color="tertiary">
                {webhook.active ? 'Active' : 'Inactive'}
              </Text>
              <ToggleSwitch
                checked={webhook.active}
                onChange={(e) => onToggleActive(webhook, e.target.checked)}
              />
            </Flex>
            <Button size="sm" kind="danger" onClick={() => onDelete(webhook)}>
              Delete
            </Button>
          </Flex>
        </Flex>
      </Flex>
    </Box>
  );
});

WebhookCard.displayName = 'WebhookCard';

const WebhooksPage: FC = memo(() => {
  const [webhooks, setWebhooks] = useState<WebhookSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedWebhook, setSelectedWebhook] = useState<WebhookSubscription | null>(null);

  const fetchWebhooks = async () => {
    try {
      setLoading(true);
      setError(null);
      const data: WebhookSubscriptionsResponse = await apiClient.get('/api/webhook-subscriptions');
      setWebhooks(data?.subscriptions || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch webhooks');
      setWebhooks([]); // Ensure we have an empty array on error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const handleCreateSuccess = (webhook: WebhookSubscription) => {
    setWebhooks((prev) => [...prev, webhook]);
    // Don't close modal here - let user manually close after copying secret
  };

  const handleToggleActive = async (webhook: WebhookSubscription, active: boolean) => {
    try {
      const updateRequest: UpdateWebhookRequest = { url: webhook.url, active };
      const updatedWebhook: WebhookSubscription = await apiClient.put<WebhookSubscription>(
        `/api/webhook-subscriptions/${webhook.id}`,
        updateRequest
      );
      setWebhooks((prev) => prev.map((w) => (w.id === updatedWebhook.id ? updatedWebhook : w)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update webhook');
      // Revert the optimistic update by refetching
      fetchWebhooks();
    }
  };

  const handleDeleteSuccess = () => {
    if (selectedWebhook) {
      setWebhooks((prev) => prev.filter((w) => w.id !== selectedWebhook.id));
    }
    setDeleteModalOpen(false);
    setSelectedWebhook(null);
  };

  const handleDelete = (webhook: WebhookSubscription) => {
    setSelectedWebhook(webhook);
    setDeleteModalOpen(true);
  };

  return (
    <>
      <Flex width="100%" direction="column" gap={32}>
        {/* Header Section */}
        <Flex direction="column">
          <SectionHeader title="Webhooks" />
          <SectionContainer>
            <Flex direction="row" align="center" justify="space-between">
              <Flex direction="column" gap={8}>
                <Text fontSize="md" fontWeight="semibold">
                  Webhook Subscriptions
                </Text>
                <Text fontSize="sm" color="tertiary">
                  Receive notifications when documents are indexed or changed in your Grapevine
                  instance. Webhooks are sent via HTTP POST with HMAC signature verification.
                  {DOCS_URL && (
                    <>
                      {' '}
                      <a
                        href={`${DOCS_URL}/features/webhooks`}
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
              <Button onClick={() => setCreateModalOpen(true)} kind="primary">
                Create Webhook
              </Button>
            </Flex>
          </SectionContainer>
        </Flex>

        {/* Webhooks List */}
        <Flex direction="column">
          <SectionHeader title="Your Webhook Subscriptions" />
          {loading ? (
            <Flex justify="center" align="center" direction="column" gap={16} py={32}>
              <Loader size="md" />
              <Text fontSize="md" color="tertiary">
                Loading webhook subscriptions...
              </Text>
            </Flex>
          ) : error ? (
            <Flex direction="column" gap={16}>
              <Text color="dangerPrimary">Error: {error}</Text>
              <Button onClick={fetchWebhooks} kind="secondary">
                Retry
              </Button>
            </Flex>
          ) : (webhooks?.length || 0) === 0 ? (
            <SectionContainer>
              <Flex direction="column" gap={8} align="center" py={32}>
                <Text color="tertiary">No webhook subscriptions yet</Text>
              </Flex>
            </SectionContainer>
          ) : (
            <Flex direction="column" gap={12}>
              {(webhooks || []).map((webhook) => (
                <WebhookCard
                  key={webhook.id}
                  webhook={webhook}
                  onToggleActive={handleToggleActive}
                  onDelete={handleDelete}
                />
              ))}
            </Flex>
          )}
        </Flex>
      </Flex>

      <CreateWebhookModal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onSuccess={handleCreateSuccess}
      />

      <DeleteWebhookModal
        webhook={selectedWebhook}
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setSelectedWebhook(null);
        }}
        onSuccess={handleDeleteSuccess}
      />
    </>
  );
});

WebhooksPage.displayName = 'WebhooksPage';

export { WebhooksPage };
