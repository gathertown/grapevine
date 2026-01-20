import React from 'react';
import { Flex } from '@gathertown/gather-design-system';

interface StepProgressBarProps {
  totalSteps: number;
  currentStep: number;
  completedSteps?: number;
  showStepNumbers?: boolean;
  maxWidth?: string;
  height?: string;
  backgroundColor?: string;
  gradient?: string;
}

const StepProgressBar: React.FC<StepProgressBarProps> = ({
  totalSteps,
  currentStep,
  completedSteps = currentStep - 1,
  showStepNumbers = false,
  maxWidth = '180px',
  height = '8px',
  backgroundColor = '#f3f4f6',
  gradient = 'linear-gradient(90deg, #B79AD9 0%, #764BB5 100%)',
}) => {
  // Calculate progress percentage based on completed steps
  const progressPercentage = Math.min((completedSteps / totalSteps) * 100, 100);

  if (showStepNumbers) {
    return (
      <Flex direction="column" gap={8} style={{ width: '100%', alignItems: 'center' }}>
        {/* Step Numbers */}
        <Flex gap={8} style={{ alignItems: 'center' }}>
          {Array.from({ length: totalSteps }, (_, index) => {
            const stepNumber = index + 1;
            const isCompleted = stepNumber <= completedSteps;
            const isCurrent = stepNumber === currentStep;

            return (
              <React.Fragment key={stepNumber}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '12px',
                    fontWeight: '500',
                    backgroundColor: isCompleted ? '#5E2DA1' : isCurrent ? '#E8D3FF' : '#f3f4f6',
                    color: isCompleted ? 'white' : isCurrent ? '#5E2DA1' : '#9CA3AF',
                    border: isCurrent && !isCompleted ? '2px solid #5E2DA1' : 'none',
                  }}
                >
                  {isCompleted ? '✓' : stepNumber}
                </div>
                {index < totalSteps - 1 && (
                  <div
                    style={{
                      width: '24px',
                      height: '2px',
                      backgroundColor: stepNumber < currentStep ? '#5E2DA1' : '#f3f4f6',
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </Flex>

        {/* Progress Bar */}
        <div
          style={{
            width: '100%',
            maxWidth,
            height,
            backgroundColor,
            borderRadius: '4px',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <div
            style={{
              width: `${progressPercentage}%`,
              height: '100%',
              background: gradient,
              borderRadius: '4px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </Flex>
    );
  }

  return (
    <Flex style={{ width: '100%', alignItems: 'center', justifyContent: 'center' }}>
      <div
        style={{
          width: '100%',
          maxWidth,
          height,
          backgroundColor,
          borderRadius: '4px',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            width: `${progressPercentage}%`,
            height: '100%',
            background: gradient,
            borderRadius: '4px',
            transition: 'width 0.3s ease',
          }}
        />
      </div>
    </Flex>
  );
};

export { StepProgressBar };
