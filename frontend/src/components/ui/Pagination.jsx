export default function Pagination({ page, totalPages, total, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <div style={{
      display: "flex", justifyContent: "center", alignItems: "center",
      gap: 8, marginTop: 16, fontSize: 10, color: "var(--color-text-secondary)",
    }}>
      <button
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={page === 1}
        style={{
          padding: "2px 8px", borderRadius: 4, fontSize: 10,
          border: "0.5px solid var(--color-border-secondary)",
          background: "var(--color-background-secondary)",
          color: page === 1 ? "var(--color-text-secondary)" : "var(--color-text-primary)",
          cursor: page === 1 ? "not-allowed" : "pointer",
        }}
      >
        ← Back
      </button>
      <span>Page {page} of {totalPages} · {total} total</span>
      <button
        onClick={() => onChange(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        style={{
          padding: "2px 8px", borderRadius: 4, fontSize: 10,
          border: "0.5px solid var(--color-border-secondary)",
          background: "var(--color-background-secondary)",
          color: page === totalPages ? "var(--color-text-secondary)" : "var(--color-text-primary)",
          cursor: page === totalPages ? "not-allowed" : "pointer",
        }}
      >
        Next →
      </button>
    </div>
  );
}
