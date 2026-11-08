/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: '#0B1F3A', soft: '#17335A', tint: '#EEF2F7' },
        brandgreen: { DEFAULT: '#12B76A', dark: '#0E9156', tint: '#E7F8F0' },
        canvas: '#F6F8FB',
        hairline: '#E3E9F2',
        muted: '#5A6B85',
        warn: '#F79009',
        dangr: '#D92D20',
      },
      borderRadius: { xl2: '20px' },
      boxShadow: { card: '0 4px 14px rgba(11,31,58,0.06)' },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
