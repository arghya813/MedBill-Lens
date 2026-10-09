/**
 * ESLint configuration.
 *
 * Deliberately small. `tsc --noEmit` already runs with `noUnusedLocals` and
 * `noUnusedParameters`, so ESLint only covers what a type checker cannot see:
 * hook dependency arrays, genuine mistakes and consistency.
 *
 * Type-aware notes:
 *  - `no-undef` is off because TypeScript resolves globals such as
 *    `RequestInit` and `AbortController` that ESLint does not know about.
 *  - `no-unused-vars` comes from `@typescript-eslint`, not the base rule: the
 *    base rule reports every interface and type alias as an unused variable.
 *  - `react-hooks/exhaustive-deps` is a warning, not an error. Two call sites
 *    intentionally narrow a dependency and carry a comment explaining why.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  plugins: ["react-hooks", "@typescript-eslint"],
  extends: ["eslint:recommended"],
  ignorePatterns: ["dist", "node_modules", "*.config.js", "*.cjs", "src/vite-env.d.ts"],
  rules: {
    "no-undef": "off",
    "no-unused-vars": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        args: "after-used",
        ignoreRestSiblings: true,
      },
    ],
    "no-console": ["warn", { allow: ["warn", "error"] }],
    eqeqeq: ["error", "smart"],
    "no-implicit-coercion": "error",
    "prefer-const": "error",
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
  },
  overrides: [
    {
      files: ["**/*.cjs"],
      env: { node: true },
      rules: { "no-undef": "off" },
    },
  ],
};
