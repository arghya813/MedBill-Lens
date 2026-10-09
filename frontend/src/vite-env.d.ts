/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin. Leave unset in development to use the Vite proxy. */
  readonly VITE_API_BASE_URL?: string;
  /** Backend origin the dev server proxies `/api` to. Defaults to 127.0.0.1:8000. */
  readonly VITE_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
