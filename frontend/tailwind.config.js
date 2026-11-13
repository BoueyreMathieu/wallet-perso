/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Fond de l'appli (clair / sombre) et couleur d'accent (violet).
        surface: { DEFAULT: "#f6f5fb", dark: "#0b1020" },
        panel: { DEFAULT: "#ffffff", dark: "#141a2e" },
        accent: {
          50: "#f3f1ff", 100: "#e9e5ff", 200: "#d4cdff", 300: "#b4a6ff", 400: "#9177ff",
          500: "#7552f5", 600: "#6236e8", 700: "#5228c9", 800: "#4422a3", 900: "#391f82",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 16px rgba(16, 24, 40, 0.06)",
      },
    },
  },
  plugins: [],
};
