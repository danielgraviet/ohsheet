import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: path.resolve(import.meta.dirname),
  base: '/static/setup-app/',
  build: {
    outDir: path.resolve(import.meta.dirname, '../../app/static/setup-app'),
    emptyOutDir: true,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
});
