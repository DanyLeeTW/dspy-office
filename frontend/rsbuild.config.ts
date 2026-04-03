import { defineConfig } from '@rsbuild/core';
import { pluginReact } from '@rsbuild/plugin-react';
import dotenv from 'dotenv';

// Load .env.local file
dotenv.config({ path: '.env.local' });

export default defineConfig({
  plugins: [pluginReact()],
  html: {
    template: './index.html',
  },
  source: {
    entry: {
      index: './src/index.tsx',
    },
    define: {
      // Always empty — the dev proxy rewrites /api/* to the backend.
      // VITE_API_BASE_URL in .env.local is only used as the proxy target below.
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(''),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8080',
        changeOrigin: true,
        timeout: 120000, // 2 minutes for slow embedding API
      },
    },
  },
});
