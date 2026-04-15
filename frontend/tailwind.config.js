/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink:   { 950: "#07090d", 900: "#0b0e14", 800: "#11151d", 700: "#161b26", 600: "#1d2330", 500: "#2a3140", 400: "#4a5264" },
        accent: { 400: "#5eead4", 500: "#2dd4bf", 600: "#14b8a6" },
        signal: { red: "#f43f5e", amber: "#f59e0b", green: "#10b981", cyan: "#06b6d4", violet: "#a855f7" },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(94,234,212,0.25), 0 12px 32px -12px rgba(94,234,212,0.25)",
        panel: "0 0 0 1px rgba(255,255,255,0.04), 0 8px 24px -12px rgba(0,0,0,0.5)",
      },
      keyframes: {
        pulseRing: {
          "0%":   { transform: "scale(0.8)", opacity: "0.9" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        flicker: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.5" },
        },
      },
      animation: {
        pulseRing: "pulseRing 1.8s ease-out infinite",
        flicker:   "flicker 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
