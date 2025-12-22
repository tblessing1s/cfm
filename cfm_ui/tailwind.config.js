/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        'surface-3': 'var(--surface-3)',
        text: 'var(--text)',
        muted: 'var(--text-muted)',
        soft: 'var(--text-soft)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        accent: 'var(--accent)',
        'accent-strong': 'var(--accent-strong)',
        danger: 'var(--danger)',
        success: 'var(--success)',
        warning: 'var(--warning)',
      },
      boxShadow: {
        deck: '0 18px 30px var(--shadow)',
      },
      fontFamily: {
        display: ['Space Grotesk', 'IBM Plex Sans', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
