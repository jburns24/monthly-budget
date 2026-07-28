import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Deliberately no `allowedHosts` entry, and adding one would be a trap:
    // Vite's default ([]) already permits `localhost`, `*.localhost` and every
    // bare IP, which covers both callers in the k3d stack -- the browser
    // arrives through Traefik with `Host: localhost:8080`, and the kubelet
    // readiness probe dials the pod IP. Narrowing it to a hostname list would
    // start 403-ing the probe, surfacing as a pod that never goes Ready.
    host: true,
    port: 5173,
    // Fail loudly instead of drifting to 5174 — the k8s Service and Tilt
    // port-forward both target 5173.
    strictPort: true,
    // Tilt live_update extracts files into the container's overlayfs, which
    // does not reliably raise inotify events. Polling is opt-in via env so
    // host-native `npm run dev` keeps using the cheaper native watcher.
    watch:
      process.env.VITE_USE_POLLING === 'true' ? { usePolling: true, interval: 300 } : undefined,
    hmr: {
      // In-cluster the dev server listens on 5173, but the browser reaches it
      // through the Traefik ingress on localhost:8080. Without clientPort the
      // HMR websocket would dial 5173 on the browser's origin and hang.
      clientPort: process.env.VITE_HMR_CLIENT_PORT
        ? Number(process.env.VITE_HMR_CLIENT_PORT)
        : undefined,
      protocol: process.env.VITE_HMR_PROTOCOL ?? undefined,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/setupTests.ts'],
    css: true,
    server: {
      deps: {
        inline: [/@chakra-ui/, /framer-motion/],
      },
    },
  },
})
