import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(() => {
  const apiBase = process.env.VITE_API_BASE
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: apiBase
        ? undefined
        : {
            '/api': {
              target: 'http://localhost:8000',
              changeOrigin: true,
              rewrite: (path) => path.replace(/^\/api/, ''),
            },
          },
    },
    test: {
      globals: true,
      environment: 'happy-dom',
      setupFiles: './src/tests/setup.ts',
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        exclude: [
          'node_modules/',
          'src/tests/',
          '**/*.test.{ts,tsx}',
          '**/*.spec.{ts,tsx}',
          '**/types/',
          'vite.config.ts',
          'eslint.config.js',
        ],
        thresholds: {
          lines: 65,
          functions: 65,
          branches: 50,
          statements: 65,
        },
      },
    },
  }
})
