/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        sage: {
          50:  "#f2f6f1",
          100: "#e0eade",
          200: "#c3d5bf",
          300: "#9ab896",
          400: "#729870",
          500: "#5B7553",
          600: "#496042",
          700: "#3a4d34",
          800: "#2e3d28",
          900: "#233020",
        },
        emergency: "#C53030",
        urgent:    "#DD6B20",
        routine:   "#D69E2E",
        selfcare:  "#38A169",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        arabic: ['"IBM Plex Sans Arabic"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.07), 0 1px 2px -1px rgb(0 0 0 / 0.05)",
        "card-md": "0 4px 12px -2px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.04)",
      },
    },
  },
  plugins: [
    require("tailwindcss-rtl"),
  ],
}
