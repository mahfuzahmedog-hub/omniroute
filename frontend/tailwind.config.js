/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        forge: {
          bg: "#0b0f17",
          panel: "#121826",
          border: "#1f2937",
          accent: "#f97316",
        },
      },
    },
  },
  plugins: [],
};
