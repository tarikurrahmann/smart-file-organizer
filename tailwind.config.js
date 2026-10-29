/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./electron-app/**/*.{html,js}", "./Website/**/*.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "sans-serif"]
      },
      colors: {
        ink: "#080d19",
        panel: "#111a2b",
        muted: "#8995aa",
        mint: "#6ee7c2"
      },
      boxShadow: {
        glow: "0 0 70px rgba(109, 91, 255, 0.18)",
        card: "0 20px 70px rgba(0, 0, 0, 0.24)"
      }
    }
  },
  plugins: []
};
