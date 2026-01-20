import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tsconfigPaths from 'vite-tsconfig-paths';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { vanillaExtractPlugin as vanillaExtractPluginEsbuild } from '@vanilla-extract/esbuild-plugin';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  const backendPort = Number(env.ADMIN_WEB_UI_BACKEND_PORT) || 5002;
  const frontendPort = Number(env.ADMIN_WEB_UI_FRONTEND_PORT) || 5173;

  return {
    plugins: [react(), tsconfigPaths(), vanillaExtractPlugin({ identifiers: 'short' })],
    optimizeDeps: {
      esbuildOptions: {
        plugins: [vanillaExtractPluginEsbuild({ runtime: true, identifiers: 'debug' })],
      },
    },
    server: {
      host: true,
      port: frontendPort,
      strictPort: true, // Fail if port is in use instead of trying another port
      proxy: {
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
