import { AvatarProps } from 'src/components/base/Avatar/Avatar';

export type AvatarItem = Omit<AvatarProps, 'size'> & {
  key: string;
};
