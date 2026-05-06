import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listEnrichedPosts } from "../api/client";
import { Shield, AlertTriangle, Search } from "lucide-react";

const SEVERITY_OPTS = ["", "HIGH", "MED", "LOW"];

const SEV_STYLE = {
  HIGH: { bg: "var(--color-red-bg)",   color: "var(--color-red-text)"   },
  MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)" },
  LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)" },
};

const SENT_STYLE = {
  negative: { color: "var(--color-red-text)",   bg: "var(--color-red-bg)"   },
  positive: { color: "var(--color-green-text)", bg: "var(--color-green-bg)" },
  neutral:  { color: "var(--color-text-secondary)", bg: "var(--color-background-secondary)" },
};

function PostCard({ post }) {
  const sc = SENT_STYLE[post.sentiment] || SENT_STYLE.neutral;
  const drugs    = post.drugs    || [];
  const symptoms = post.symptoms || [];
  const sev = SEV_STYLE[post.safety_severity];

  return (
    <div style={{ padding: "7px 0", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
      {/* Top row */}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 3 }}>
        {post.has_safety_signal && sev && (
          <span style={{ fontSize: 9, padding: "2px 5px", borderRadius: 3, fontWeight: 500, flexShrink: 0, background: sev.bg, color: sev.color }}>
            {post.safety_severity}
          </span>
        )}
        <div style={{ fontSize: 10, color: "var(--color-text-primary)", lineHeight: 1.4, flex: 1 }}>
          {post.clean_text?.length > 240 ? post.clean_text.slice(0, 240) + "…" : post.clean_text}
        </div>
      </div>

      {/* Entities */}
      {(drugs.length > 0 || symptoms.length > 0) && (
        <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginBottom: 4 }}>
          {drugs.slice(0, 3).map((d) => (
            <span key={d} style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-blue-bg)", color: "var(--color-blue-text)" }}>
              {d}
            </span>
          ))}
          {symptoms.slice(0, 3).map((s) => (
            <span key={s} style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-amber-bg)", color: "var(--color-amber-text)" }}>
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Meta */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 9, color: "var(--color-text-secondary)" }}>
        <span style={{ padding: "1px 5px", borderRadius: 2, background: sc.bg, color: sc.color }}>
          {post.sentiment}
          {post.sentiment_score != null ? ` ${post.sentiment_score > 0 ? "+" : ""}${post.sentiment_score.toFixed(2)}` : ""}
        </span>
        {post.has_pii && (
          <span style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--color-amber)" }}>
            <Shield size={10} /> PII
          </span>
        )}
        {post.is_duplicate && <span>duplicate</span>}
        {post.language && post.language !== "en" && <span>lang: {post.language}</span>}
        <span style={{ marginLeft: "auto" }}>{new Date(post.processed_at).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

export default function Posts() {
  const { projectId } = useParams();
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [drugFilter, setDrugFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["enriched-posts", projectId, page, severity, drugFilter],
    queryFn: () => listEnrichedPosts(projectId, { page, page_size: 20, severity: severity || undefined, drug: drugFilter || undefined }),
    keepPreviousData: true,
  });

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 1;

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>Post feed</span>
        <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>{total} posts</span>

        <select value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }} style={{
          fontSize: 10, padding: "3px 6px", borderRadius: 4,
          border: "0.5px solid var(--color-border-secondary)",
          background: "var(--color-background-secondary)",
          color: "var(--color-text-primary)", cursor: "pointer",
        }}>
          {SEVERITY_OPTS.map((s) => <option key={s} value={s}>{s || "All severities"}</option>)}
        </select>

        <div style={{ display: "flex", alignItems: "center", gap: 5, border: "0.5px solid var(--color-border-secondary)", borderRadius: 4, padding: "3px 8px", background: "var(--color-background-secondary)" }}>
          <Search size={11} color="var(--color-text-secondary)" />
          <input
            placeholder="Filter by drug…"
            value={drugFilter}
            onChange={(e) => { setDrugFilter(e.target.value); setPage(1); }}
            style={{ background: "none", border: "none", outline: "none", fontSize: 10, color: "var(--color-text-primary)", width: 120 }}
          />
        </div>
      </div>

      {/* Feed */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 12px" }}>
        {isLoading ? (
          <div style={{ padding: "40px 0", textAlign: "center", fontSize: 10, color: "var(--color-text-secondary)" }}>Loading posts…</div>
        ) : items.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}>
            <AlertTriangle size={24} color="var(--color-text-secondary)" style={{ marginBottom: 8 }} />
            <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>No posts found for this filter.</div>
          </div>
        ) : (
          items.map((post) => <PostCard key={post.id} post={post} />)
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 8, padding: "8px", borderTop: "0.5px solid var(--color-border-tertiary)", fontSize: 10, color: "var(--color-text-secondary)", flexShrink: 0 }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-secondary)", color: page === 1 ? "var(--color-text-secondary)" : "var(--color-text-primary)", cursor: page === 1 ? "not-allowed" : "pointer" }}>← Back</button>
          <span>Page {page} of {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-secondary)", color: page === totalPages ? "var(--color-text-secondary)" : "var(--color-text-primary)", cursor: page === totalPages ? "not-allowed" : "pointer" }}>Next →</button>
        </div>
      )}
    </div>
  );
}
