/** @type {import("tailwindcss").Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,ts,tsx}"],
  theme: {
    extend: {
      // One neutral, engineering-tool palette, exposed as semantic names so a
      // component asks for "surface" or "border" rather than picking a slate
      // shade. A single accent replaces the previous cyan+violet pairing:
      // two accents made every panel compete for the eye.
      colors: {
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        raised: "var(--color-raised)",
        sunken: "var(--color-sunken)",
        line: "var(--color-line)",
        "line-strong": "var(--color-line-strong)",
        ink: "var(--color-ink)",
        "ink-muted": "var(--color-ink-muted)",
        "ink-faint": "var(--color-ink-faint)",
        accent: "var(--color-accent)",
        "accent-soft": "var(--color-accent-soft)",
        // Hex rather than var() for the status hues, so opacity modifiers such
        // as `bg-danger/10` compile; the CSS variables keep the same values.
        ok: "#3baa7a",
        warn: "#c89a43",
        danger: "#d46a78",
      },
      borderRadius: {
        // Panels 8px, controls 6px. Nothing larger: the previous 2rem cards are
        // what read as a template rather than a tool.
        panel: "8px",
        control: "6px",
      },
      maxWidth: {
        // Past roughly this width the eye loses the line. Expressed in rem, not
        // ch: `ch` is the width of "0", which made a CJK line ~46 characters.
        reading: "46rem",
      },
    },
  },
  plugins: [],
};
