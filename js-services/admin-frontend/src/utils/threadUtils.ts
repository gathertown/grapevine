export type ChannelType = 'channel' | 'dm';

export interface ChannelInfo {
  type: ChannelType;
  display: string;
  isChannel: boolean;
}

export const getChannelType = (channelId: string): ChannelType => {
  return channelId.startsWith('C') ? 'channel' : 'dm';
};

export const formatChannelDisplay = (channelId: string, channelName?: string): string => {
  if (!channelId.startsWith('C')) {
    return '💬 DM';
  }
  return channelName ? `#${channelName}` : `#${channelId}`;
};

export const isChannel = (channelId: string): boolean => {
  return channelId.startsWith('C');
};

export const getChannelInfo = (channelId: string, channelName?: string): ChannelInfo => {
  const type = getChannelType(channelId);
  return {
    type,
    display: formatChannelDisplay(channelId, channelName),
    isChannel: isChannel(channelId),
  };
};

export const formatUserDisplay = (
  userId: string,
  userName?: string,
  userDisplayName?: string
): string => {
  if (userDisplayName) {
    return userDisplayName;
  }
  if (userName) {
    return `@${userName}`;
  }
  return userId;
};

export const truncateText = (text: string, maxLength = 200): string => {
  if (text.length <= maxLength) return text;
  return `${text.substring(0, maxLength)}...`;
};

export const needsExpansion = (text: string, maxLength: number): boolean => {
  return text.length > maxLength;
};

export const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleString();
};
