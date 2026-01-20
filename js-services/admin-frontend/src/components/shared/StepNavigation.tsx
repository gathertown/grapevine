import React, { type FC } from 'react';
import { Flex, Button, Tooltip } from '@gathertown/gather-design-system';

interface StepNavigationProps {
  isFirstStep: boolean;
  isLastStep: boolean;
  isStepValid: boolean;
  isLoading?: boolean;
  onPreviousStep: () => void;
  onNextStep: () => void;
  nextButtonText?: string;
  previousButtonText?: string;
  completionButtonText?: string;
  disabled?: boolean;
  justify?: 'flex-start' | 'center' | 'flex-end' | 'space-between';
  nextButtonStyle?: React.CSSProperties;
  /** Tooltip text to show when next button is disabled */
  disabledTooltip?: string;
  /** Hide the complete button on the last step */
  hideComplete?: boolean;
  /** Hide the next/complete button entirely */
  hideNextButton?: boolean;
}

export const StepNavigation: FC<StepNavigationProps> = ({
  isFirstStep,
  isLastStep,
  isStepValid,
  isLoading = false,
  onPreviousStep,
  onNextStep,
  nextButtonText = 'Next →',
  previousButtonText = 'Previous',
  completionButtonText = 'Complete Setup',
  disabled = false,
  justify = 'flex-end',
  nextButtonStyle,
  disabledTooltip,
  hideComplete = false,
  hideNextButton = false,
}) => {
  const getNextButtonText = () => {
    if (isLastStep) return completionButtonText;
    return nextButtonText;
  };

  const isNextDisabled = !isStepValid || isLoading || disabled;

  return (
    <Flex justify={justify} align="center" gap={16}>
      {!isFirstStep && (
        <Button kind="secondary" onClick={onPreviousStep} disabled={isLoading || disabled}>
          {previousButtonText}
        </Button>
      )}
      {!hideNextButton && !(isLastStep && hideComplete) && (
        <Tooltip
          content={isNextDisabled && disabledTooltip ? disabledTooltip : undefined}
          disabled={!isNextDisabled || !disabledTooltip}
        >
          <div>
            <Button
              kind="primary"
              onClick={onNextStep}
              disabled={isNextDisabled}
              style={{ minWidth: '120px', ...nextButtonStyle }}
              fullWidth
            >
              {getNextButtonText()}
            </Button>
          </div>
        </Tooltip>
      )}
    </Flex>
  );
};
