const { generateESLintConfigForPackage } = require("../../.eslintrc.lib.cjs")
module.exports = generateESLintConfigForPackage(__dirname, true, [
  {
    files: ["*"],
    rules: {
      "@gathertown/prefer-logger-over-console": "warn",
      "@gathertown/i18n-wrapper-checks": "error",
      "@gathertown/i18n-enforce-placeholders": [
        "error",
        {
          // ignore tags defined with `defaultRichTextElements` in `src/i18n/t.tsx`
          ignoreList: ["b", "br", "u", "gt", "X"],
        },
      ],
    },
    extends: ["plugin:storybook/recommended"],
  },
  {
    // Generated icon components are pre-memoized by SVGR during build time,
    // but use a different memoization pattern than our @gathertown/require-memo rule expects.
    // We disable the rule here since these components are already optimized.
    files: ["src/components/**/generated/**"],
    rules: {
      "@gathertown/require-memo": "off",
    },
  },
])
