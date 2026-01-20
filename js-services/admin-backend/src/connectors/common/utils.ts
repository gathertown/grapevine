import { ConfigValue } from '../../config/types';

const configString = (value: ConfigValue): string => {
  return typeof value === 'string' ? value : '';
};

export { configString };
