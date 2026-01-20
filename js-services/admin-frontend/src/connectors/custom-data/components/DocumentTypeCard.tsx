import type { MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import {
  type CustomDocumentType,
  CustomDocumentTypeState,
  useCustomDocumentTypeStats,
} from '../customDataApi';
import { customDataPath } from '../customDataRoutes';
import { StatusBadge, CustomFieldsCountBadge, IngestEndpointDisplay } from './shared';

interface DocumentTypeCardProps {
  documentType: CustomDocumentType;
  tenantId: string;
  onEdit: () => void;
  onDelete: () => void;
  onToggleState: () => void;
  isToggling?: boolean;
}

export const DocumentTypeCard = ({
  documentType,
  tenantId,
  onEdit,
  onDelete,
  onToggleState,
  isToggling,
}: DocumentTypeCardProps) => {
  const navigate = useNavigate();
  const { data: stats } = useCustomDocumentTypeStats(documentType.id);
  const isEnabled = documentType.state === CustomDocumentTypeState.ENABLED;

  const customFieldsCount = documentType.custom_fields?.fields?.length || 0;
  const documentCount = stats?.documentCount ?? 0;

  const handleCardClick = () => {
    navigate(`${customDataPath}/types/${documentType.id}`);
  };

  const handleButtonClick = (e: MouseEvent, action: () => void) => {
    e.stopPropagation();
    action();
  };

  return (
    <div
      onClick={handleCardClick}
      style={{
        padding: '16px',
        backgroundColor: '#ffffff',
        borderRadius: '8px',
        border: '1px solid #dee2e6',
        cursor: 'pointer',
        transition: 'border-color 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#6366f1';
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(99, 102, 241, 0.1)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#dee2e6';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <Flex direction="column" gap={12}>
        {/* Header row */}
        <Flex direction="row" style={{ justifyContent: 'space-between', alignItems: 'start' }}>
          <Flex direction="column" gap={4}>
            <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
              <Text fontSize="md" fontWeight="semibold">
                {documentType.display_name}
              </Text>
              <StatusBadge state={documentType.state} />
              <CustomFieldsCountBadge count={customFieldsCount} />
            </Flex>
            {/* Description */}
            {documentType.description && (
              <Text fontSize="sm" color="secondary">
                {documentType.description}
              </Text>
            )}
          </Flex>

          <Flex direction="row" gap={8}>
            <Button
              onClick={(e) => handleButtonClick(e, onToggleState)}
              kind="secondary"
              size="sm"
              loading={isToggling}
            >
              {isEnabled ? 'Disable' : 'Enable'}
            </Button>
            <Button onClick={(e) => handleButtonClick(e, onEdit)} kind="secondary" size="sm">
              Edit
            </Button>
            <Button onClick={(e) => handleButtonClick(e, onDelete)} kind="danger" size="sm">
              Delete
            </Button>
          </Flex>
        </Flex>

        {/* Meta row */}
        <Flex direction="row" gap={16} style={{ alignItems: 'center' }}>
          <Text fontSize="xs" color="secondary">
            <strong>Documents:</strong> {documentCount}
          </Text>
          <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
            <Text fontSize="xs" color="secondary">
              <strong>Endpoint:</strong>
            </Text>
            <IngestEndpointDisplay tenantId={tenantId} slug={documentType.slug} variant="inline" />
          </Flex>
        </Flex>
      </Flex>
    </div>
  );
};
