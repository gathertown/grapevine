import { Text, Flex, Box } from '@gathertown/gather-design-system';
import { theme } from '@gathertown/gather-design-foundations';
import controlYourDataGif from '../assets/images/control_your_data.gif';
import deleteYourDataGif from '../assets/images/delete_your_data.gif';
import indexDataSvg from '../assets/images/index_data.svg';
import { useCompletedSourcesCount } from '../contexts/OnboardingContext';
import styles from './HomePageSubtitle.module.css';

export const HomePageSubtitle = () => {
  const completedSourcesCount = useCompletedSourcesCount();

  const cards = [
    {
      description: `You control what data to share with Grapevine when setting up any integration`,
      bg: theme.bg.accentTertiary,
      src: controlYourDataGif,
      style: { transform: 'scale(1.03)' },
    },
    {
      description: `Grapevine will not index anything that is not publicly accessible in your org`,
      bg: theme.bg.successTertiary,
      src: indexDataSvg,
      style: { width: 132 },
    },
    {
      description: <>You can delete your data with one click from Settings, at anytime</>,
      bg: theme.bg.dangerTertiary,
      src: deleteYourDataGif,
      style: { transform: 'scale(1.03)' },
    },
  ];
  return (
    <Flex direction="column" gap={8}>
      <Text color="tertiary">As you get setup, here are a couple of things to keep in mind</Text>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 12,
        }}
      >
        {cards.map((card, index) => (
          <div
            key={card.bg + index}
            style={{ border: `1px solid ${theme.border.tertiary}`, backgroundColor: card.bg }}
            className={`${styles.onboardingInfoCard} ${completedSourcesCount > 0 ? styles.completedStepOne : ''}`}
          >
            <Flex
              justify="center"
              align="center"
              style={{ height: 122, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}
              overflow="hidden"
            >
              <img
                src={card.src}
                alt="illustration"
                style={{ width: '100%', objectFit: 'contain', ...card.style }}
              />
            </Flex>
            <Box px={12} pt={8} pb={12} style={{ borderTop: `1px solid ${theme.border.tertiary}` }}>
              <Text as="p" color="tertiary" fontSize="sm" textAlign="center">
                {card.description}
              </Text>
            </Box>
          </div>
        ))}
      </div>
    </Flex>
  );
};
