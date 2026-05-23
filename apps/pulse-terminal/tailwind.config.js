/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Syne"', 'system-ui', 'sans-serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        pulse: {
          bg: '#04060d',
          panel: 'rgba(12, 16, 28, 0.72)',
          border: 'rgba(148, 163, 184, 0.12)',
          gold: '#d4af37',
          cyan: '#22d3ee',
          mint: '#34d399',
          rose: '#fb7185',
          amber: '#fbbf24',
        },
      },
      boxShadow: {
        glow: '0 0 40px rgba(34, 211, 238, 0.08)',
        gold: '0 0 32px rgba(212, 175, 55, 0.12)',
      },
      animation: {
        'ticker': 'ticker 40s linear infinite',
        'flash-up': 'flashUp 0.6s ease-out',
        'flash-down': 'flashDown 0.6s ease-out',
      },
      keyframes: {
        ticker: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        flashUp: {
          '0%': { backgroundColor: 'rgba(52, 211, 153, 0.35)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashDown: {
          '0%': { backgroundColor: 'rgba(251, 113, 133, 0.35)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
    },
  },
  plugins: [],
};
