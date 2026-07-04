/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{ts,tsx,css}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        eyes: {
          primary: {
            DEFAULT: 'var(--eyes-primary)',
            hover: 'var(--eyes-primary-hover)',
            light: 'var(--eyes-primary-light)',
          },
          success: {
            DEFAULT: 'var(--eyes-success)',
            hover: 'var(--eyes-success-hover)',
            light: 'var(--eyes-success-light)',
          },
          warning: {
            DEFAULT: 'var(--eyes-warning)',
            hover: 'var(--eyes-warning-hover)',
            light: 'var(--eyes-warning-light)',
          },
          danger: {
            DEFAULT: 'var(--eyes-danger)',
            hover: 'var(--eyes-danger-hover)',
            light: 'var(--eyes-danger-light)',
          },
          bg: {
            page: 'var(--eyes-bg-page)',
            sidebar: 'var(--eyes-bg-sidebar)',
            card: 'var(--eyes-bg-card)',
            'card-hover': 'var(--eyes-bg-card-hover)',
            input: 'var(--eyes-bg-input)',
          },
          text: {
            primary: 'var(--eyes-text-primary)',
            secondary: 'var(--eyes-text-secondary)',
            muted: 'var(--eyes-text-muted)',
          },
          border: {
            DEFAULT: 'var(--eyes-border)',
            hover: 'var(--eyes-border-hover)',
          },
        },
      },
      borderRadius: {
        eyes: 'var(--eyes-radius)',
        'eyes-sm': 'var(--eyes-radius-sm)',
        'eyes-lg': 'var(--eyes-radius-lg)',
        'eyes-xl': 'var(--eyes-radius-xl)',
      },
      spacing: {
        'eyes': 'var(--eyes-spacing)',
        'eyes-sm': 'var(--eyes-spacing-sm)',
        'eyes-xs': 'var(--eyes-spacing-xs)',
      },
      fontFamily: {
        eyes: 'var(--eyes-font-family)',
      },
      fontSize: {
        'eyes-xs': 'var(--eyes-font-size-xs)',
        'eyes-sm': 'var(--eyes-font-size-sm)',
        'eyes-base': 'var(--eyes-font-size-base)',
        'eyes-md': 'var(--eyes-font-size-md)',
        'eyes-lg': 'var(--eyes-font-size-lg)',
        'eyes-xl': 'var(--eyes-font-size-xl)',
        'eyes-2xl': 'var(--eyes-font-size-2xl)',
        'eyes-3xl': 'var(--eyes-font-size-3xl)',
      },
      boxShadow: {
        'eyes-sm': 'var(--eyes-shadow-sm)',
        'eyes': 'var(--eyes-shadow)',
        'eyes-lg': 'var(--eyes-shadow-lg)',
        'eyes-xl': 'var(--eyes-shadow-xl)',
      },
      transitionDuration: {
        'eyes-fast': 'var(--eyes-transition-fast)',
        'eyes': 'var(--eyes-transition)',
        'eyes-slow': 'var(--eyes-transition-slow)',
      },
      zIndex: {
        'eyes-dropdown': '1000',
        'eyes-modal': '1050',
        'eyes-toast': '1080',
      },
    },
  },
  plugins: [],
}
