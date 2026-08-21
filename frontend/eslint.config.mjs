// eslint-config-next ships a flat config directly. Going through
// FlatCompat instead trips a circular-reference crash in its schema
// validator on this version.
import next from "eslint-config-next";

const config = [
  ...next,
  { ignores: [".next/**", "node_modules/**"] },
];

export default config;
