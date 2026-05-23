/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PULSE_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
