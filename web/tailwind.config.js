/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        honey: {
          50: "#fff8e1",
          100: "#ffecb3",
          200: "#ffe082",
          300: "#ffd54f",
          400: "#ffca28",
          500: "#ffc107",
          600: "#ffb300",
          700: "#ffa000",
          800: "#ff8f00",
          900: "#ff6f00",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "Helvetica Neue",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
