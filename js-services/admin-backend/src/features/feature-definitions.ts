import { getGrapevineEnv } from '@corporate-context/backend-common';

enum FeatureKeys {
  DUMMY_FEATURE = 'dummy:feature',
  CONNECTOR_TRELLO = 'connector:trello',
  INTERNAL_FEATURES = 'internal:features',
  CONNECTOR_MONDAY = 'connector:monday',
  CONNECTOR_PIPEDRIVE = 'connector:pipedrive',
  CONNECTOR_FIGMA = 'connector:figma',
  CONNECTOR_POSTHOG = 'connector:posthog',
  CONNECTOR_CANVA = 'connector:canva',
  CONNECTOR_TEAMWORK = 'connector:teamwork',
}

type FeatureKey = FeatureKeys;
type GrapevineEnvironment = 'local' | 'staging' | 'production';

interface FeatureMetadata {
  environments: GrapevineEnvironment[];
}

const FEATURE_METADATA: Record<FeatureKey, FeatureMetadata> = {
  [FeatureKeys.DUMMY_FEATURE]: {
    environments: ['local'],
  },
  [FeatureKeys.CONNECTOR_TRELLO]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.INTERNAL_FEATURES]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_MONDAY]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_PIPEDRIVE]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_FIGMA]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_POSTHOG]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_CANVA]: {
    environments: ['local', 'staging'],
  },
  [FeatureKeys.CONNECTOR_TEAMWORK]: {
    environments: ['local', 'staging'],
  },
};

const isFeatureKey = (featureKey: string): featureKey is FeatureKey => {
  return ALL_FEATURE_KEYS.includes(featureKey as FeatureKey);
};

const getCurrentEnv = (): GrapevineEnvironment => {
  const env = getGrapevineEnv();

  if (env === 'staging') {
    return 'staging';
  }

  if (env === 'production' || env === 'prod') {
    return 'production';
  }

  return 'local';
};

const isFeatureAllowedInEnv = (feature: FeatureKey): boolean => {
  const env = getCurrentEnv();
  const metadata = FEATURE_METADATA[feature];

  if (!metadata) {
    return false;
  }

  return metadata.environments.includes(env);
};

const ALL_FEATURE_KEYS = Object.keys(FEATURE_METADATA) as FeatureKey[];

export { ALL_FEATURE_KEYS, isFeatureAllowedInEnv, isFeatureKey, type FeatureKey, FeatureKeys };
