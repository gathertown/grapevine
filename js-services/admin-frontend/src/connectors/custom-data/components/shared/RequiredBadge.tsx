interface RequiredBadgeProps {
  show?: boolean;
}

export const RequiredBadge = ({ show = true }: RequiredBadgeProps) => {
  if (!show) return null;

  return <span style={{ fontSize: '12px', color: '#dc3545', marginLeft: '4px' }}>Required</span>;
};
