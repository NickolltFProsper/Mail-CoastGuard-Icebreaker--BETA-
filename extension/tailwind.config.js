/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./panel.js",
    "./popup.html",
    "./popup.js"
  ],
  theme: {
    extend: {
      colors: {
        uneti: {
          navy: "#1D2B5B",
          turquoise: "#22A7B4",
          orange: "#F15A24",
          yellow: "#FBB827",
          purple: "#5E2D79",
          green: "#3FA535",
          bg: "#F4F6FA",
          surface: "#FFFFFF",
          border: "#E1E5EE"
        },
        mcg: {
          black: "#111111",
          blackBg: "#ECECEC",
          red: "#D32F2F",
          redBg: "#FDECEA",
          yellow: "#F9A825",
          yellowBg: "#FFF8E1",
          green: "#2E7D32",
          greenBg: "#E8F5E9"
        }
      }
    }
  },
  safelist: [
    "mcg-level-BLACK",
    "mcg-level-RED",
    "mcg-level-YELLOW",
    "mcg-level-GREEN"
  ],
  plugins: []
};
