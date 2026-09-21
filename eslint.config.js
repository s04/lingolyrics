const js = require("@eslint/js");
const globals = require("globals");
module.exports = [
  {
    ignores: [
      "static/vendor/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  {
    files: ["static/app.js"],
    languageOptions: { globals: globals.browser },
    rules: { "no-unused-vars": ["error", { caughtErrors: "none" }] },
  },
  {
    files: ["tests/browser/**/*.js", "*.config.js"],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
];
