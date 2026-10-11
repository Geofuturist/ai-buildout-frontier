import type { Config } from "tailwindcss";

// Colours come from CSS variables in app/globals.css (SPEC_WEB section 6).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--surface)",
        water: "var(--water)",
        ink: "var(--ink)",
        ink2: "var(--ink-2)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        line: "var(--line)",
      },
    },
  },
  plugins: [],
};
export default config;
