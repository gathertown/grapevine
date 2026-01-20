import { Flex } from '@gathertown/gather-design-system';
import { CustomDocumentTypeState } from '../../customDataApi';
import { STATUS_STYLES } from './styles';

interface StatusBadgeProps {
  state: CustomDocumentTypeState;
}

export const StatusBadge = ({ state }: StatusBadgeProps) => {
  const isEnabled = state === CustomDocumentTypeState.ENABLED;
  const styles = isEnabled ? STATUS_STYLES.enabled : STATUS_STYLES.disabled;
  const label = isEnabled ? 'Enabled' : 'Disabled';

  return (
    <Flex
      style={{
        padding: '2px 8px',
        backgroundColor: styles.backgroundColor,
        borderRadius: '4px',
        border: `1px solid ${styles.borderColor}`,
      }}
    >
      <span
        style={{
          fontSize: '12px',
          color: styles.textColor,
        }}
      >
        {label}
      </span>
    </Flex>
  );
};
