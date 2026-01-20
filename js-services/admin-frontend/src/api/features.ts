import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';

type FeatureKey =
  | 'connector:gather'
  | 'connector:trello'
  | 'internal:features'
  | 'connector:monday'
  | 'connector:pipedrive'
  | 'connector:figma'
  | 'connector:posthog'
  | 'connector:canva'
  | 'connector:teamwork';

type FeatureMap = Record<FeatureKey, boolean>;

interface FeaturesResponse {
  tenantId: string;
  features: FeatureMap;
}

const fetchFeatures = (): Promise<FeatureMap> =>
  apiClient.get<FeaturesResponse>('/api/features').then(({ features }) => features);

const featuresQueryKey = ['features'];

const useFeatures = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: featuresQueryKey,
    queryFn: fetchFeatures,
  });

  return { data, isLoading, error };
};

const useIsFeatureEnabled = (featureKey: FeatureKey) => {
  const { data: featuresData, ...rest } = useFeatures();

  const isEnabled = featuresData ? featuresData[featureKey] : undefined;

  return {
    data: isEnabled,
    ...rest,
  };
};

export { useFeatures, useIsFeatureEnabled, featuresQueryKey, type FeatureKey, type FeatureMap };
