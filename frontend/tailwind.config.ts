import type { Config } from "tailwindcss";

/**
 * CrowdWise design tokens.
 *
 * The palette is deliberately restrained: a deep slate ground, one confident
 * teal accent for actions, and semantic colours reserved for status. It should
 * read as a trustworthy fintech product, not a speculative crypto site — so no
 * neon, no gradient-on-everything, and colour is used to mean something.
 */
const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1rem", sm: "1.5rem", lg: "2rem" },
      screens: { "2xl": "1280px" },
    },
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0F172A",
          soft: "#1E293B",
          muted: "#475569",
          faint: "#94A3B8",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          subtle: "#F8FAFC",
          muted: "#F1F5F9",
          border: "#E2E8F0",
        },
        brand: {
          50: "#ECFDF7",
          100: "#D1FAE9",
          200: "#A7F3D5",
          300: "#6EE7BC",
          400: "#34D3A0",
          500: "#10B583",
          600: "#059669",
          700: "#047857",
          800: "#065F46",
          900: "#064E3B",
        },
        accent: {
          50: "#EEF2FF",
          100: "#E0E7FF",
          300: "#A5B4FC",
          500: "#6366F1",
          600: "#4F46E5",
          700: "#4338CA",
        },
        positive: { soft: "#DCFCE7", DEFAULT: "#16A34A", strong: "#15803D" },
        caution: { soft: "#FEF3C7", DEFAULT: "#D97706", strong: "#B45309" },
        critical: { soft: "#FEE2E2", DEFAULT: "#DC2626", strong: "#B91C1C" },
        neutralState: { soft: "#F1F5F9", DEFAULT: "#64748B" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        lg: "0.75rem",
        xl: "1rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
        lift: "0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)",
        popover: "0 10px 30px -10px rgba(15, 23, 42, 0.25)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
