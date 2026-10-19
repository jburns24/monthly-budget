/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Frontend release version, baked in at image build time (build-push.yaml). */
  readonly VITE_APP_VERSION?: string
}
