import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['haynes-mark.svg'],
      manifest: {
        name: 'Haynes Inventory',
        short_name: 'Inventory',
        description: 'Warehouse inventory and material requests',
        theme_color: '#17221b',
        background_color: '#f2f3ef',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/haynes-mark.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
