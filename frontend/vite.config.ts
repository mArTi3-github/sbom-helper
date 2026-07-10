import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    VueI18nPlugin({
      include: [path.resolve(__dirname, 'src/i18n/locales/**')],
    }),
  ],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'https://localhost:8443',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})