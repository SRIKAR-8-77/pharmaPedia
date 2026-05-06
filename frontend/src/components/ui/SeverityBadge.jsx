const MAP = {
  HIGH: { bg: "var(--color-red-bg)",   color: "var(--color-red-text)"   },
  MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)" },
  LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)" },
};

export default function SeverityBadge({ severity }) {
  if (!severity) return null;
  const c = MAP[severity] || MAP.LOW;
  return (
    <span style={{
      background: c.bg, color: c.color,
      fontSize: 9, fontWeight: 500,
      padding: "2px 5px", borderRadius: 3, flexShrink: 0,
    }}>
      {severity}
    </span>
  );
}
