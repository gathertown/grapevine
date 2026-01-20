const canvaAccessTokenConfigKey = 'CANVA_ACCESS_TOKEN';
const canvaUserIdConfigKey = 'CANVA_USER_ID';
const canvaUserDisplayNameConfigKey = 'CANVA_USER_DISPLAY_NAME';

type CanvaConfig = {
  [canvaAccessTokenConfigKey]?: string;
  [canvaUserIdConfigKey]?: string;
  [canvaUserDisplayNameConfigKey]?: string;
};

export {
  type CanvaConfig,
  canvaAccessTokenConfigKey,
  canvaUserIdConfigKey,
  canvaUserDisplayNameConfigKey,
};
