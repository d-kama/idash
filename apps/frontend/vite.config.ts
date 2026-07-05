import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // ローカル結合確認: `/api` を task bff（uvicorn:8000）へプロキシする。
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
