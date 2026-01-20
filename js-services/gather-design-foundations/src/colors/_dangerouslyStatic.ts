import { colorTokens } from '../tokens/colors';
import { GatherDesignSystemColors } from './colorContract.css';

// Static colors are the same between modes
export const dangerouslyStatic = {
  // White with transparency
  alphaWhite2: colorTokens.alphaWhite2,
  alphaWhite3: colorTokens.alphaWhite3,
  alphaWhite5: colorTokens.alphaWhite5,
  alphaWhite7: colorTokens.alphaWhite7,
  alphaWhite10: colorTokens.alphaWhite10,
  alphaWhite20: colorTokens.alphaWhite20,
  alphaWhite30: colorTokens.alphaWhite30,
  alphaWhite40: colorTokens.alphaWhite40,
  alphaWhite50: colorTokens.alphaWhite50,
  alphaWhite60: colorTokens.alphaWhite60,
  alphaWhite70: colorTokens.alphaWhite70,
  alphaWhite80: colorTokens.alphaWhite80,
  alphaWhite90: colorTokens.alphaWhite90,
  white: colorTokens.white,

  // Black with transparency
  alphaBlack2: colorTokens.alphaBlack2,
  alphaBlack3: colorTokens.alphaBlack3,
  alphaBlack5: colorTokens.alphaBlack5,
  alphaBlack7: colorTokens.alphaBlack7,
  alphaBlack10: colorTokens.alphaBlack10,
  alphaBlack20: colorTokens.alphaBlack20,
  alphaBlack30: colorTokens.alphaBlack30,
  alphaBlack40: colorTokens.alphaBlack40,
  alphaBlack50: colorTokens.alphaBlack50,
  alphaBlack60: colorTokens.alphaBlack60,
  alphaBlack70: colorTokens.alphaBlack70,
  alphaBlack80: colorTokens.alphaBlack80,
  alphaBlack90: colorTokens.alphaBlack90,
  black: colorTokens.black,
} as const satisfies GatherDesignSystemColors['dangerouslyStatic'];
