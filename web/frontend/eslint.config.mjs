// Flat config for ESLint 9 (required by eslint-config-next 16).
// eslint-config-next 16 ships a native flat config, so spread it directly
// (FlatCompat on it hits a circular-JSON bug).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [
  { ignores: ["node_modules/", ".next/", "out/", "public/", "scripts/", "**/*.d.ts"] },
  ...nextCoreWebVitals,
  {
    // eslint-plugin-react-hooks v6 (pulled in by eslint-config-next 16) ships
    // React-Compiler-era rules that flag valid patterns and are only meant for
    // codebases that have adopted the React Compiler. This project has not, so
    // they are not part of our lint contract. Every mainstream rule
    // (rules-of-hooks, exhaustive-deps, next/*) stays enabled and is kept clean.
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-hooks/immutability": "off",
    },
  },
];

export default config;
