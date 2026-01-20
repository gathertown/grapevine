/* eslint-disable @typescript-eslint/consistent-type-assertions */
/* eslint-disable @gathertown/require-memo */

import React, { useState } from 'react';

import { darkMode, lightMode, theme, tokens } from '@gathertown/gather-design-foundations';
import { Box, Flex, Gothify, Icon, IconName, Label, Text, ToggleSwitch } from '../index';

interface ColorDisplayProps {
  label: string;
}

interface IconColorSectionProps {
  title: string;
  colors: Record<string, string>;
  iconName: string;
  themeKey: string;
  showRawValue: boolean;
}

const ROW_HEIGHT = 32;

function getBackgroundColorForKey(key: string) {
  if (key.includes('OnLight')) return theme.bg.primaryLight;

  if (key.includes('OnDark')) return theme.bg.primaryDark;

  if (key.includes('OnDanger')) return theme.bg.dangerPrimary;

  if (key.includes('OnAccent')) return theme.bg.accentPrimary;

  return 'transparent';
}

const Title = ({ title }: { title: string }) => (
  <h2
    style={{
      color: theme.text.primary,
      borderColor: theme.border.secondary,
      marginBottom: 20,
      paddingBottom: 12,
    }}
  >
    {title}
  </h2>
);

const TokenName = ({ tokenName }: { tokenName: string }) => (
  <div style={{ fontSize: tokens.fontSize.xs, fontFamily: 'monospace' }}>theme.{tokenName}</div>
);

const TokenValue = ({ value, style }: { value: string; style?: React.CSSProperties }) => (
  <div style={{ fontSize: tokens.fontSize.xs, fontFamily: 'monospace', ...style }}>{value}</div>
);

const renderIconColorSection = ({
  title,
  colors,
  iconName,
  themeKey,
  showRawValue,
}: IconColorSectionProps) => (
  <div key={themeKey}>
    <Title title={title} />

    <Flex gap={4} direction="column">
      {Object.entries(colors).map(([key, color]) => (
        <Flex key={key} height={ROW_HEIGHT} gap={12} align="center" style={{ color }}>
          <Icon name={iconName as IconName} />
          <TokenName tokenName={`${themeKey}.${key}`} />
          {showRawValue && <TokenValue value={color} style={{ marginLeft: 'auto' }} />}
        </Flex>
      ))}
    </Flex>
  </div>
);

export const ColorDisplay: React.FC<ColorDisplayProps> = () => {
  const [selectedAppearance, setSelectedAppearance] = useState(lightMode);
  const [showRawValue, setShowRawValue] = useState(true);

  const renderTextColors = (colors: Record<string, string>) => (
    <div key="text">
      <Title title="Text Colors" />
      <Flex gap={4} direction="column">
        {Object.entries(colors).map(([key, color]) => (
          <Flex
            key={key}
            style={{ color, backgroundColor: getBackgroundColorForKey(key) }}
            height={ROW_HEIGHT}
            borderRadius={10}
            justify="space-between"
            align="center"
            px={8}
          >
            <TokenName tokenName={`text.${key}`} />
            {showRawValue && <TokenValue value={color} />}
          </Flex>
        ))}
      </Flex>
    </div>
  );

  const renderForegroundColors = (colors: Record<string, string>) => (
    <div key="fg">
      <Title title="Foreground Colors" />
      <Flex gap={4} direction="column">
        {Object.entries(colors).map(([key, color]) => {
          const backgroundColor = getBackgroundColorForKey(key);
          return (
            <Flex key={key} height={ROW_HEIGHT} gap={12} align="center">
              <Flex
                borderRadius={10}
                align="center"
                justify="center"
                height="100%"
                style={{
                  color,
                  backgroundColor,
                  aspectRatio: 1,
                }}
              >
                <Icon name="palette" />
              </Flex>
              <TokenName tokenName={`fg.${key}`} />
              {showRawValue && <TokenValue value={color} style={{ marginLeft: 'auto' }} />}
            </Flex>
          );
        })}
      </Flex>
    </div>
  );

  const renderBackgroundColors = (colors: Record<string, string>) => (
    <div key="bg">
      <Title title="Background Colors" />
      <Flex gap={4} direction="column">
        {Object.entries(colors).map(([key, color]) => (
          <Flex
            key={key}
            style={{
              backgroundColor: color,
              color: key.includes('Dark') ? theme.text.primaryOnDark : 'inherit',
            }}
            height={ROW_HEIGHT}
            borderRadius={10}
            justify="space-between"
            align="center"
            px={8}
          >
            <TokenName tokenName={`bg.${key}`} />
            {showRawValue && <TokenValue value={color} />}
          </Flex>
        ))}
      </Flex>
    </div>
  );

  const renderBorderColors = (colors: Record<string, string>) => (
    <div key="border">
      <Title title="Border Colors" />
      <Flex gap={4} direction="column">
        {Object.entries(colors).map(([key, color]) => (
          <Flex
            key={key}
            style={{
              border: `1px solid ${color}`,
              backgroundColor: key.includes('Dark') ? theme.bg.secondaryDark : 'transparent',
              color: key.includes('Dark') ? theme.text.primaryOnDark : 'inherit',
            }}
            height={ROW_HEIGHT}
            borderRadius={10}
            justify="space-between"
            align="center"
            px={8}
          >
            <TokenName tokenName={`border.${key}`} />
            {showRawValue && <TokenValue value={color} />}
          </Flex>
        ))}
      </Flex>
    </div>
  );

  const renderShadowColors = (colors: Record<string, string>) => (
    <div key="border">
      <Title title="Shadow Colors" />
      <Flex gap={4} direction="column">
        {Object.entries(colors).map(([key, color]) => (
          <Flex
            key={key}
            style={{
              backgroundColor: color,
            }}
            height={ROW_HEIGHT}
            borderRadius={10}
            justify="space-between"
            align="center"
            px={8}
          >
            <TokenName tokenName={`shadow.${key}`} />
            {showRawValue && <TokenValue value={color} />}
          </Flex>
        ))}
      </Flex>
    </div>
  );

  const renderDangerouslyStaticColors = (colors: Record<string, string>) => (
    <div key="fg" style={{ width: '100%', gridColumn: '1 / -1' }}>
      <Title title="Dangerously Static Colors" />
      <Box pb={12}>
        <Text fontSize="sm" as="p">
          These colors are static and ignore the current theme. Each corresponds to the alpha
          percentage visible. For example, `theme.dangerouslyStatic.alphaWhite20` is pure white
          (#FFFFFF) as 20% opacity.
        </Text>
      </Box>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          columnGap: '48px',
          rowGap: 4,
        }}
      >
        {Object.entries(colors).map(([key, color], index) => {
          const isWhiteOrAlphaWhite = key.includes('white') || key.includes('alphaWhite');
          return (
            <Flex
              key={key}
              height={ROW_HEIGHT}
              gap={12}
              align="center"
              borderRadius={12}
              px={2}
              py={2}
              style={{
                gridColumn: Math.floor(index / (Object.entries(colors).length / 2)) + 1,
                gridRow: (index % Math.ceil(Object.entries(colors).length / 2)) + 1,
                backgroundColor: isWhiteOrAlphaWhite ? theme.bg.primaryDark : 'inherit',
                color: isWhiteOrAlphaWhite ? theme.text.primaryOnDark : 'inherit',
              }}
            >
              <Flex
                borderRadius={10}
                align="center"
                justify="center"
                height="100%"
                style={{
                  backgroundColor: color,
                  aspectRatio: 1,
                }}
              />
              <TokenName tokenName={`dangerouslyStatic.${key}`} />
            </Flex>
          );
        })}
      </div>
    </div>
  );

  const renderPresenceColors = (colors: Record<string, string>) =>
    renderIconColorSection({
      title: 'Presence Colors',
      colors,
      iconName: 'user',
      themeKey: 'presence',
      showRawValue,
    });

  const renderEventStatusColors = (colors: Record<string, string>) =>
    renderIconColorSection({
      title: 'Event Status Colors',
      colors,
      iconName: 'calendar',
      themeKey: 'eventStatus',
      showRawValue,
    });

  const renderUiColors = (colors: Record<string, string>) =>
    renderIconColorSection({
      title: 'UI Colors',
      colors,
      iconName: 'paletteOutlined',
      themeKey: 'ui',
      showRawValue,
    });

  const renderMapColors = (colors: Record<string, string>) =>
    renderIconColorSection({
      title: 'Map Colors',
      colors,
      iconName: 'map',
      themeKey: 'map',
      showRawValue,
    });

  return (
    <Flex direction="column" gap={36} mt={36} mx={-36}>
      <Flex align="center" gap={36} mx={36}>
        <Flex align="center" gap={8}>
          <ToggleSwitch
            id="appearance-toggle"
            name="appearance-toggle"
            checked={selectedAppearance === darkMode}
            onChange={() =>
              setSelectedAppearance(selectedAppearance === darkMode ? lightMode : darkMode)
            }
          />
          <Label htmlFor="appearance-toggle">Dark mode</Label>
        </Flex>
        <Flex align="center" gap={8}>
          <ToggleSwitch
            id="raw-value-toggle"
            name="raw-value-toggle"
            checked={showRawValue}
            onChange={() => setShowRawValue(!showRawValue)}
          />
          <Label htmlFor="raw-value-toggle">Show raw value</Label>
        </Flex>
      </Flex>

      <Gothify enabled={selectedAppearance === darkMode}>
        <Box
          backgroundColor={selectedAppearance === darkMode ? 'primary' : 'secondary'}
          p={36}
          borderRadius={16}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 48 }}>
            {selectedAppearance.text && renderTextColors(selectedAppearance.text)}
            {selectedAppearance.fg && renderForegroundColors(selectedAppearance.fg)}
            {selectedAppearance.bg && renderBackgroundColors(selectedAppearance.bg)}
            {selectedAppearance.border && renderBorderColors(selectedAppearance.border)}
            {selectedAppearance.shadow && renderShadowColors(selectedAppearance.shadow)}
            {selectedAppearance.dangerouslyStatic &&
              renderDangerouslyStaticColors(selectedAppearance.dangerouslyStatic)}
            {selectedAppearance.presence && renderPresenceColors(selectedAppearance.presence)}
            {selectedAppearance.eventStatus &&
              renderEventStatusColors(selectedAppearance.eventStatus)}
            {selectedAppearance.ui && renderUiColors(selectedAppearance.ui)}
            {selectedAppearance.map && renderMapColors(selectedAppearance.map)}
          </div>
        </Box>
      </Gothify>
    </Flex>
  );
};
