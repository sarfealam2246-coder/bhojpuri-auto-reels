/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        fbBlue: '#1877F2',
        fbBg: '#F0F2F5',
        fbBorder: '#CED0D4',
        fbGreen: '#42B72A',
        fbText: '#050505',
        fbMuted: '#65676B',
      },
    },
  },
  plugins: [],
};
