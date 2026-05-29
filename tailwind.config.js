/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          '"Microsoft YaHei"',
          '"PingFang SC"',
          'sans-serif'
        ],
        serif: ['Georgia', 'ui-serif', 'serif'],
        mono: ['Courier New', 'Courier', 'monospace'],
      },
      boxShadow: {
        'soft': '0 2px 12px -3px rgba(0, 0, 0, 0.04), 0 1px 4px -2px rgba(0, 0, 0, 0.02)',
        'card': '0 4px 20px -2px rgba(0, 0, 0, 0.03), 0 2px 8px -1px rgba(0, 0, 0, 0.02)',
        'neon-blue': '0 0 15px rgba(59, 130, 246, 0.5)',
        'neon-yellow': '0 0 15px rgba(234, 179, 8, 0.6)',
      }
    },
  },
  plugins: [],
}
