import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: { '/api': process.env.VITE_API_PROXY_TARGET || 'http://localhost:5000', '/auth': process.env.VITE_API_PROXY_TARGET || 'http://localhost:5000' },
  },
});
