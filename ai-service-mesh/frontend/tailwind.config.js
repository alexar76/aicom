/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        mesh: {
          bg: '#060612',
          panel: 'rgba(255,255,255,0.04)',
          accent: '#22d3ee',
          violet: '#a78bfa',
          ok: '#34d399',
          warn: '#fbbf24',
        },
      },
      boxShadow: {
        glow: '0 0 40px -10px rgba(34, 211, 238, 0.35)',
      },
    },
  },
  plugins: [],
};
