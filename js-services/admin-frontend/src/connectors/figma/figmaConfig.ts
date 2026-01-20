const figmaAccessTokenConfigKey = 'FIGMA_ACCESS_TOKEN';
const figmaUserEmailConfigKey = 'FIGMA_USER_EMAIL';
const figmaUserHandleConfigKey = 'FIGMA_USER_HANDLE';

type FigmaConfig = {
  [figmaAccessTokenConfigKey]?: string;
  [figmaUserEmailConfigKey]?: string;
  [figmaUserHandleConfigKey]?: string;
};

export {
  type FigmaConfig,
  figmaAccessTokenConfigKey,
  figmaUserEmailConfigKey,
  figmaUserHandleConfigKey,
};
