import { memo } from 'react';
import type { FC, ReactNode } from 'react';
import { Flex, Text, Box } from '@gathertown/gather-design-system';

interface OnboardingStepProps {
  stepNumber: number;
  children: ReactNode;
  isComplete?: boolean;
  label?: string;
}

const OnboardingStep: FC<OnboardingStepProps> = memo(
  ({ stepNumber, children, isComplete, label }) => {
    return (
      <Flex direction="column" gap={8}>
        {/* Step Label */}
        <Flex align="center" gap={8}>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            color={isComplete ? 'successPrimary' : 'tertiary'}
          >
            {isComplete ? '✅ ' : ''} {label || `STEP ${stepNumber}`}
          </Text>
        </Flex>

        {/* Step Content with Border */}
        <Box
          borderColor={isComplete ? 'successPrimary' : 'tertiary'}
          borderRadius={8}
          p={16}
          borderWidth={1}
          borderStyle="solid"
          style={{
            transition: 'all 0.2s ease-in-out',
          }}
        >
          {children}
        </Box>
      </Flex>
    );
  }
);

OnboardingStep.displayName = 'OnboardingStep';

export { OnboardingStep };
