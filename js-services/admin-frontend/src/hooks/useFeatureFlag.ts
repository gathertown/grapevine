export type FeatureFlag = 'flag-billing-ui';

export const useFeatureFlag = (flagName: FeatureFlag): boolean => {
  return localStorage.getItem(flagName) === 'true';
};
