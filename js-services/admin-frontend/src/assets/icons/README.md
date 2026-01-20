# Company Icons

This directory contains SVG icons for the various data source companies in the admin web UI.

## Current Status

All files contain placeholder SVGs with the same designs as the inline components. **You need to replace these with official company icons.**

## Download Instructions

Replace each placeholder file with the official company icon:

### 1. Slack (`slack.svg`)

- **Official Source**: https://slack.com/media-kit
- **Alternative**: https://brandfolder.com/slack/logos
- **Format**: SVG with `fill="currentColor"` for theming

### 2. Notion (`notion.svg`)

- **Official Source**: https://brandfetch.com/notion.so
- **Alternative**: https://commons.wikimedia.org/wiki/File:Notion-logo.svg
- **Format**: SVG with `fill="currentColor"` for theming

### 3. Linear (`linear.svg`)

- **Official Source**: https://linear.app/brand
- **Alternative**: https://brandfetch.com/linear.app
- **Format**: SVG with `fill="currentColor"` for theming

### 4. Google Drive (`google-drive.svg`)

- **Official Source**: https://commons.wikimedia.org/wiki/File:Google_Drive_icon_(2020).svg
- **Alternative**: https://worldvectorlogo.com/logo/google-drive
- **Format**: SVG with `fill="currentColor"` for theming

## Important Notes

1. **Size**: All icons should be 24x24px or scalable
2. **Color**: Use `fill="currentColor"` to inherit the brand color from CSS
3. **Format**: SVG format only
4. **Optimization**: Remove unnecessary attributes and minimize file size
5. **Licensing**: Ensure you have proper rights to use the logos

## File Structure

```
src/assets/icons/
├── README.md
├── slack.svg
├── notion.svg
├── linear.svg
└── google-drive.svg
```

## Usage

Icons are automatically imported in `DataSources.jsx` using React's SVG import:

```javascript
import { ReactComponent as SlackIcon } from '../assets/icons/slack.svg';
```

The icons inherit their color from the `color` property defined in the `dataSources` array, maintaining each company's brand colors.
