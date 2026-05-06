const TYPE_MAP = {
  drug:    { bg: "var(--color-blue-bg)",   color: "var(--color-blue-text)"  },
  symptom: { bg: "var(--color-amber-bg)",  color: "var(--color-amber-text)" },
  meddra:  { bg: "var(--color-green-bg)",  color: "var(--color-green-text)" },
  source:  { bg: "var(--color-purple-bg)", color: "var(--color-purple-text)"},
};

export default function EntityPill({ label, type = "drug" }) {
  const c = TYPE_MAP[type] || { bg: "var(--color-background-secondary)", color: "var(--color-text-secondary)" };
  return (
    <span style={{
      fontSize: 9, padding: "1px 4px", borderRadius: 2,
      background: c.bg, color: c.color,
      display: "inline-flex", alignItems: "center",
    }}>
      {label}
    </span>
  );
}
