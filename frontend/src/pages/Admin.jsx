import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getPipelineHealth, listPiiQueue, reviewPiiItem,
  discoverSources, getAuditLog, listSignalReview, getSignalReviewCounts,
  triageSignal, getComplianceReport, getComplianceSettings, updateComplianceSettings,
  runRetentionPurge, gdprErase, getRbacModel,
} from "../api/client";
import api from "../api/client";
import { Search, RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock, Bot, Download, Trash2, Settings, Users, Lock } from "lucide-react";
import Pagination from "../components/ui/Pagination";

// ── Shared ────────────────────────────────────────────────────────────────────

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 2, borderBottom: "0.5px solid var(--color-border-tertiary)", marginBottom: 16 }}>
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} style={{
          padding: "5px 10px", border: "none", background: "none",
          fontSize: 11, cursor: "pointer", fontWeight: active === t.key ? 500 : 400,
          color: active === t.key ? "var(--color-text-primary)" : "var(--color-text-secondary)",
          borderBottom: `1.5px solid ${active === t.key ? "var(--color-text-primary)" : "transparent"}`,
          display: "flex", alignItems: "center", gap: 5,
        }}>
          <t.icon size={12} /> {t.label}
        </button>
      ))}
    </div>
  );
}

function StatusDot({ status }) {
  const c = { healthy: "var(--color-green)", degraded: "var(--color-amber)", error: "var(--color-red)", paused: "var(--color-border-secondary)" };
  return <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: c[status] || "var(--color-border-secondary)", flexShrink: 0 }} />;
}

function AdminCard({ title, children }) {
  return (
    <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "10px" }}>
      <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 8, color: "var(--color-text-primary)" }}>{title}</div>
      {children}
    </div>
  );
}

function AdminRow({ label, value, dot }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 10 }}>
      <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--color-text-secondary)", flex: 1 }}>
        {dot && <StatusDot status={dot} />}
        {label}
      </span>
      <span style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

// ── Pipeline Health ───────────────────────────────────────────────────────────

const TIER_INFO = {
  1: { label: "Tier 1 · Official API", color: "var(--color-green)" },
  2: { label: "Tier 2 · RSS Feed",     color: "var(--color-blue)"  },
  3: { label: "Tier 3 · Social API",   color: "var(--color-amber)" },
  4: { label: "Tier 4 · Web Scraper",  color: "var(--color-red)"   },
};

function PipelineHealth() {
  const { data, isLoading, refetch } = useQuery({ queryKey: ["pipeline-health"], queryFn: getPipelineHealth, refetchInterval: 30000 });
  const { data: scraperData } = useQuery({ queryKey: ["scrapers"], queryFn: () => api.get("/admin/scrapers").then((r) => r.data) });
  const scrapers = scraperData?.registered || [];
  const knownHtmlSites = scraperData?.known_html_sites || [];

  const summary = { healthy: 0, degraded: 0, error: 0, paused: 0 };
  data?.sources?.forEach((s) => { summary[s.status] = (summary[s.status] || 0) + 1; });

  return (
    <div>
      {/* Overview grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
        <AdminCard title="Pipeline health">
          {isLoading ? (
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>Loading…</div>
          ) : !data?.sources?.length ? (
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>No sources configured.</div>
          ) : (
            data.sources.map((s) => (
              <AdminRow key={s.id} label={s.name} value={`${s.posts_per_hour ?? 0} posts/hr${s.status === "error" ? " ⚠" : ""}`} dot={s.status} />
            ))
          )}
          <div style={{ display: "flex", gap: 12, padding: "5px 0", fontSize: 9, color: "var(--color-text-secondary)", marginTop: 4 }}>
            <div><span style={{ fontWeight: 500, color: "var(--color-green)" }}>{summary.healthy}</span> healthy</div>
            <div><span style={{ fontWeight: 500, color: "var(--color-amber)" }}>{summary.degraded}</span> degraded</div>
            <div><span style={{ fontWeight: 500, color: "var(--color-red)" }}>{summary.error}</span> error</div>
          </div>
        </AdminCard>

        <AdminCard title="Source engines">
          {scrapers.length === 0 ? (
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>No scrapers registered.</div>
          ) : (
            scrapers.slice(0, 6).map((s) => {
              const tier = TIER_INFO[s.tier] || TIER_INFO[4];
              return (
                <div key={s.source_type} style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 10 }}>
                  <span style={{ flex: 1, color: "var(--color-text-secondary)" }}>{s.source_type}</span>
                  <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: `${tier.color}20`, color: tier.color, fontWeight: 600 }}>T{s.tier}</span>
                  {!s.auth_required && <span style={{ fontSize: 9, color: "var(--color-green)" }}>✓</span>}
                </div>
              );
            })
          )}
          <button onClick={() => refetch()} style={{
            marginTop: 6, fontSize: 9, padding: "2px 8px", borderRadius: 3,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-secondary)", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <RefreshCw size={9} /> Refresh
          </button>
        </AdminCard>
      </div>

      {/* Source table */}
      {data?.sources?.length > 0 && (
        <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, overflow: "hidden" }}>
          <div style={{ padding: "8px 10px", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 10, fontWeight: 500 }}>
            All source connectors
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead>
              <tr style={{ background: "var(--color-background-secondary)" }}>
                {["Source", "Type", "Status", "Posts/hr", "Errors", "Last run"].map((h) => (
                  <th key={h} style={{ padding: "6px 10px", textAlign: "left", fontSize: 9, fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.sources.map((s) => (
                <tr key={s.id} style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
                  <td style={{ padding: "7px 10px", fontWeight: 500 }}>{s.name}</td>
                  <td style={{ padding: "7px 10px", color: "var(--color-text-secondary)" }}>{s.source_type}</td>
                  <td style={{ padding: "7px 10px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <StatusDot status={s.status} />{s.status}
                    </span>
                  </td>
                  <td style={{ padding: "7px 10px" }}>{s.posts_per_hour ?? "—"}</td>
                  <td style={{ padding: "7px 10px", color: s.error_count > 0 ? "var(--color-red-text)" : "var(--color-text-secondary)" }}>{s.error_count ?? 0}</td>
                  <td style={{ padding: "7px 10px", color: "var(--color-text-secondary)" }}>{s.last_run ? new Date(s.last_run).toLocaleString() : "Never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pre-configured sites */}
      {knownHtmlSites.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 8 }}>Pre-configured pharma websites</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 6 }}>
            {knownHtmlSites.map((site) => (
              <div key={site.site_key} style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 5, padding: "8px 10px" }}>
                <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 2 }}>{site.site_name}</div>
                <div style={{ fontSize: 9, color: "var(--color-blue-text)" }}>
                  <a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url?.replace("https://", "")}</a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Source Discovery ──────────────────────────────────────────────────────────

function SourceDiscovery() {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState(null);
  const [steps, setSteps] = useState([]);

  const discover = useMutation({
    mutationFn: (kw) => {
      setSteps([
        { label: "DuckDuckGo search", status: "done" },
        { label: "Fetching candidate pages", status: "spin" },
        { label: "Claude relevance scoring", status: "pending" },
        { label: "Generating YAML config", status: "pending" },
      ]);
      return discoverSources(kw);
    },
    onSuccess: (data) => {
      setResults(data);
      setSteps(prev => prev.map((s) => ({ ...s, status: "done" })));
    },
    onError: () => {
      setSteps((s) => s.map((step) => ({ ...step, status: step.status === "spin" ? "error" : step.status })));
    },
  });

  return (
    <div style={{ maxWidth: 600 }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Agentic source discovery</div>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
          Enter a keyword. The agent searches the web, evaluates candidate sources for relevance, and auto-generates scraper config.
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-secondary)", borderRadius: 5, padding: "6px 10px" }}>
          <Search size={12} color="var(--color-text-secondary)" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && keyword.trim() && discover.mutate(keyword.trim())}
            placeholder="e.g. ozempic side effects forum…"
            style={{ flex: 1, background: "none", border: "none", outline: "none", fontSize: 11, color: "var(--color-text-primary)" }}
          />
        </div>
        <button
          onClick={() => keyword.trim() && discover.mutate(keyword.trim())}
          disabled={!keyword.trim() || discover.isPending}
          style={{
            padding: "6px 14px", borderRadius: 5, fontSize: 11, fontWeight: 500,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 5,
            opacity: !keyword.trim() || discover.isPending ? 0.6 : 1,
          }}
        >
          <Bot size={12} /> {discover.isPending ? "Discovering…" : "Discover →"}
        </button>
      </div>

      {/* Agent steps */}
      {steps.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 14 }}>
          {steps.map((step, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
              background: step.status === "spin" ? "var(--color-background-primary)" : "var(--color-background-secondary)",
              border: "0.5px solid " + (step.status === "spin" ? "var(--color-border-secondary)" : "var(--color-border-tertiary)"),
              borderRadius: 5, fontSize: 10,
            }}>
              <div style={{
                width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: step.status === "done" ? "var(--color-green)" : step.status === "error" ? "var(--color-red)" : "var(--color-border-secondary)",
                ...(step.status === "spin" ? { border: "1.5px solid var(--color-purple)", background: "transparent", animation: "spin .7s linear infinite" } : {}),
              }}>
                {step.status === "done" && <CheckCircle size={10} color="#fff" />}
                {step.status === "error" && <XCircle size={10} color="#fff" />}
              </div>
              <span style={{ color: step.status === "pending" ? "var(--color-text-secondary)" : "var(--color-text-primary)" }}>
                {step.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {results && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 8 }}>
            Discovered {results.discovered_sources?.length || 0} sources for "{results.keyword}"
          </div>
          {results.discovered_sources?.map((src, i) => (
            <div key={i} style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "10px 12px", marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500 }}>{src.name || src.url}</div>
                  <a href={src.url} target="_blank" rel="noreferrer" style={{ fontSize: 9, color: "var(--color-blue-text)" }}>{src.url}</a>
                </div>
                {src.relevance_score && (
                  <div style={{ fontSize: 9, color: "var(--color-green)", fontWeight: 600 }}>
                    {Math.round(src.relevance_score * 100)}% relevant
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                {src.source_type && (
                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 2, background: "var(--color-blue-bg)", color: "var(--color-blue-text)", fontWeight: 600 }}>{src.source_type}</span>
                )}
                {!src.auth_required && (
                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 2, background: "var(--color-green-bg)", color: "var(--color-green-text)" }}>No auth</span>
                )}
              </div>
              {src.recommended_integration && (
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 6, lineHeight: 1.5 }}>{src.recommended_integration}</div>
              )}
              {(src.yaml_config || src.scraper_config_yaml) && (
                <pre style={{
                  background: "var(--color-background-secondary)", borderRadius: 4, padding: "8px 10px",
                  fontSize: 9, color: "var(--color-text-secondary)", overflow: "auto", maxHeight: 140, lineHeight: 1.6,
                  fontFamily: "var(--font-mono)",
                }}>
                  {src.yaml_config || src.scraper_config_yaml}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── PII Review ────────────────────────────────────────────────────────────────

function PIIReview() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({ queryKey: ["pii-queue", page], queryFn: () => listPiiQueue({ page, page_size: 20 }), keepPreviousData: true });
  const review = useMutation({
    mutationFn: ({ id, action }) => reviewPiiItem(id, { reviewer_action: action, reviewed_by: "admin" }),
    onSuccess: () => qc.invalidateQueries(["pii-queue"]),
  });
  const items = data?.items || [];

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>PII review queue</div>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>
          {data?.total || 0} items awaiting review — personal health information detected by Microsoft Presidio
        </div>
      </div>

      {isLoading ? (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", padding: "20px 0" }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "40px", textAlign: "center" }}>
          <CheckCircle size={24} color="var(--color-green)" style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>PII queue is empty — all posts reviewed.</div>
        </div>
      ) : (
        items.map((item) => (
          <div key={item.id} style={{ padding: "10px 0", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
            <div style={{ display: "flex", gap: 5, marginBottom: 5, flexWrap: "wrap", alignItems: "center" }}>
              {(item.pii_types || []).map((t) => (
                <span key={t} style={{ fontSize: 9, padding: "2px 5px", borderRadius: 3, background: "var(--color-amber-bg)", color: "var(--color-amber-text)", fontWeight: 500 }}>
                  ⚠ {t}
                </span>
              ))}
              <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
                Conf {item.confidence ? `${(item.confidence * 100).toFixed(0)}%` : "—"} · {new Date(item.created_at).toLocaleString()}
              </span>
            </div>
            <div style={{ fontSize: 10, color: "var(--color-text-primary)", lineHeight: 1.5, background: "var(--color-background-secondary)", borderRadius: 5, padding: "6px 8px", marginBottom: 6 }}>
              {item.redacted_text || item.original_text?.slice(0, 300) || "(text not available)"}
            </div>
            <div style={{ display: "flex", gap: 5 }}>
              <button onClick={() => review.mutate({ id: item.id, action: "approve_redacted" })} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 3, border: "0.5px solid var(--color-green)", background: "transparent", color: "var(--color-green)", cursor: "pointer" }}>Approve redacted</button>
              <button onClick={() => review.mutate({ id: item.id, action: "false_positive" })} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 3, border: "0.5px solid var(--color-border-secondary)", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer" }}>False positive</button>
              <button onClick={() => review.mutate({ id: item.id, action: "delete" })} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 3, border: "0.5px solid var(--color-red)", background: "transparent", color: "var(--color-red-text)", cursor: "pointer" }}>Delete post</button>
            </div>
          </div>
        ))
      )}
      <Pagination page={page} totalPages={data?.total_pages || 1} total={data?.total || 0} onChange={setPage} />
    </div>
  );
}

// ── Signal Review ─────────────────────────────────────────────────────────────

const TRIAGE_ACTIONS = [
  { value: "escalate", label: "Escalate",  color: "var(--color-red-text)",   bg: "var(--color-red-bg)"   },
  { value: "monitor",  label: "Monitor",   color: "var(--color-amber-text)", bg: "var(--color-amber-bg)" },
  { value: "dismiss",  label: "Dismiss",   color: "var(--color-text-secondary)", bg: "var(--color-background-secondary)" },
];

function SignalCard({ signal, onTriaged }) {
  const [action, setAction] = useState("");
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const qc = useQueryClient();

  const SEV = {
    HIGH: { bg: "var(--color-red-bg)", color: "var(--color-red-text)" },
    MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)" },
    LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)" },
  };
  const sev = SEV[signal.severity] || SEV.LOW;

  const submit = async () => {
    if (!action) return;
    setSubmitting(true);
    try {
      await triageSignal(signal.id, { triage_action: action, triage_rationale: rationale || null, reviewed_by: "analyst" });
      setDone(true);
      qc.invalidateQueries(["signal-review"]);
      qc.invalidateQueries(["signal-review-counts"]);
      setTimeout(() => onTriaged(signal.id), 600);
    } catch (e) { console.error(e); }
    finally { setSubmitting(false); }
  };

  if (done) {
    return (
      <div style={{ padding: "8px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", alignItems: "center", gap: 6 }}>
        <CheckCircle size={12} color="var(--color-green)" />
        <span style={{ fontSize: 10, color: "var(--color-green)" }}>Triaged — {signal.drug} → {signal.symptom}</span>
      </div>
    );
  }

  return (
    <div style={{ padding: "10px 0", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ fontSize: 9, padding: "2px 5px", borderRadius: 3, fontWeight: 500, background: sev.bg, color: sev.color }}>{signal.severity}</span>
        <span style={{ fontSize: 11, fontWeight: 600 }}>{signal.drug}</span>
        <span style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>→</span>
        <span style={{ fontSize: 11 }}>{signal.symptom}</span>
        {signal.causality && <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-background-secondary)", color: "var(--color-text-secondary)" }}>{signal.causality}</span>}
        <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--color-text-secondary)" }}>{new Date(signal.created_at).toLocaleDateString()}</span>
      </div>

      {/* Confidence */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: 9, color: "var(--color-text-secondary)", width: 60 }}>Confidence</span>
        <div style={{ flex: 1, height: 4, background: "var(--color-border-tertiary)", borderRadius: 2 }}>
          <div style={{ height: "100%", borderRadius: 2, width: `${Math.round((signal.confidence || 0) * 100)}%`, background: sev.color }} />
        </div>
        <span style={{ fontSize: 9, fontWeight: 600, color: sev.color }}>{Math.round((signal.confidence || 0) * 100)}%</span>
      </div>

      {/* Excerpt */}
      {signal.context_window && (
        <div style={{ background: "var(--color-background-secondary)", borderRadius: 4, padding: "6px 8px", marginBottom: 8, fontSize: 10, lineHeight: 1.5, borderLeft: `2px solid ${sev.color}` }}>
          "{signal.context_window}"
        </div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 6 }}>
        {TRIAGE_ACTIONS.map((a) => (
          <button key={a.value} onClick={() => setAction(a.value)} style={{
            padding: "3px 10px", borderRadius: 4, fontSize: 10, fontWeight: 500, cursor: "pointer",
            border: `0.5px solid ${action === a.value ? a.color : "var(--color-border-secondary)"}`,
            background: action === a.value ? a.bg : "transparent",
            color: action === a.value ? a.color : "var(--color-text-secondary)",
          }}>
            {a.label}
          </button>
        ))}
      </div>
      <textarea
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        placeholder="Optional rationale for audit trail…"
        rows={2}
        style={{
          width: "100%", background: "var(--color-background-secondary)",
          border: "0.5px solid var(--color-border-tertiary)", borderRadius: 4,
          padding: "5px 8px", fontSize: 10, color: "var(--color-text-primary)",
          resize: "vertical", outline: "none", boxSizing: "border-box", marginBottom: 6,
        }}
      />
      <button onClick={submit} disabled={!action || submitting} style={{
        padding: "4px 14px", borderRadius: 4, fontSize: 10, fontWeight: 500,
        border: "none", cursor: !action || submitting ? "not-allowed" : "pointer",
        background: action ? (TRIAGE_ACTIONS.find((a) => a.value === action)?.bg || "var(--color-background-secondary)") : "var(--color-border-tertiary)",
        color: action ? (TRIAGE_ACTIONS.find((a) => a.value === action)?.color || "var(--color-text-secondary)") : "var(--color-text-secondary)",
        opacity: !action || submitting ? 0.6 : 1,
      }}>
        {submitting ? "Submitting…" : "Submit review"}
      </button>
    </div>
  );
}

function SignalReview() {
  const [page, setPage] = useState(1);
  const [sevFilter, setSevFilter] = useState("");
  const [triaged, setTriaged] = useState(new Set());

  const { data: counts } = useQuery({ queryKey: ["signal-review-counts"], queryFn: getSignalReviewCounts, refetchInterval: 30000 });
  const { data, isLoading } = useQuery({ queryKey: ["signal-review", page, sevFilter], queryFn: () => listSignalReview({ page, page_size: 15, ...(sevFilter ? { severity: sevFilter } : {}) }), keepPreviousData: true });
  const visible = (data?.items || []).filter((s) => !triaged.has(s.id));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>Signal validation queue</div>
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>HIGH and MED signals awaiting pharmacovigilance review.</div>
        </div>
        <div style={{ display: "flex", gap: 5 }}>
          {[{ key: "", label: "All" }, { key: "HIGH", label: `HIGH (${counts?.HIGH ?? "…"})` }, { key: "MED", label: `MED (${counts?.MED ?? "…"})` }].map((f) => (
            <button key={f.key} onClick={() => { setSevFilter(f.key); setPage(1); }} style={{
              padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 500,
              border: "0.5px solid " + (sevFilter === f.key ? "var(--color-border-primary)" : "var(--color-border-secondary)"),
              background: sevFilter === f.key ? "var(--color-background-secondary)" : "transparent",
              color: sevFilter === f.key ? "var(--color-text-primary)" : "var(--color-text-secondary)", cursor: "pointer",
            }}>{f.label}</button>
          ))}
        </div>
      </div>

      {/* Counts */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 6, marginBottom: 14 }}>
        {[
          { label: "Pending HIGH", value: counts?.HIGH ?? "—", color: "var(--color-red-text)" },
          { label: "Pending MED",  value: counts?.MED  ?? "—", color: "var(--color-amber-text)" },
          { label: "Total pending", value: (counts?.HIGH ?? 0) + (counts?.MED ?? 0), color: "var(--color-blue-text)" },
        ].map((c) => (
          <div key={c.label} style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 5, padding: "6px 10px" }}>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 2 }}>{c.label}</div>
            <div style={{ fontSize: 18, fontWeight: 500, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>Loading signals…</div>
      ) : visible.length === 0 ? (
        <div style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "40px", textAlign: "center" }}>
          <CheckCircle size={24} color="var(--color-green)" style={{ marginBottom: 8 }} />
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>No signals pending review.</div>
        </div>
      ) : (
        <>
          {visible.map((s) => <SignalCard key={s.id} signal={s} onTriaged={(id) => setTriaged((prev) => new Set(prev).add(id))} />)}
          <Pagination page={page} totalPages={data?.total_pages || 1} total={data?.total || 0} onChange={setPage} />
        </>
      )}
    </div>
  );
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

function AuditLog() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({ queryKey: ["audit-log", page], queryFn: () => getAuditLog({ page, page_size: 30 }), keepPreviousData: true });
  const ACTION_C = { pii_review: "var(--color-amber)", triage: "var(--color-blue)", project_create: "var(--color-green)", pipeline_run: "var(--color-purple)" };

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>Audit log</div>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>{data?.total || 0} total events</div>
      </div>
      <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, overflow: "hidden" }}>
        {isLoading ? (
          <div style={{ padding: 24, textAlign: "center", fontSize: 10, color: "var(--color-text-secondary)" }}>Loading…</div>
        ) : !data?.items?.length ? (
          <div style={{ padding: 24, textAlign: "center", fontSize: 10, color: "var(--color-text-secondary)" }}>No audit events yet.</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead>
              <tr style={{ background: "var(--color-background-secondary)" }}>
                {["Action", "Resource", "User", "Timestamp"].map((h) => (
                  <th key={h} style={{ padding: "6px 10px", textAlign: "left", fontSize: 9, fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((log) => (
                <tr key={log.id} style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
                  <td style={{ padding: "7px 10px" }}>
                    <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 2, background: `${ACTION_C[log.action] || "var(--color-border-secondary)"}20`, color: ACTION_C[log.action] || "var(--color-text-secondary)" }}>
                      {log.action}
                    </span>
                  </td>
                  <td style={{ padding: "7px 10px", color: "var(--color-text-secondary)" }}>{log.resource_type} {log.resource_id ? `· ${log.resource_id.slice(0, 8)}…` : ""}</td>
                  <td style={{ padding: "7px 10px" }}>{log.user_id || "system"}</td>
                  <td style={{ padding: "7px 10px", color: "var(--color-text-secondary)" }}>{new Date(log.timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Pagination page={page} totalPages={data?.total_pages || 1} total={data?.total || 0} onChange={setPage} />
    </div>
  );
}

// ── Compliance ────────────────────────────────────────────────────────────────

const CHECK_S = {
  pass: { color: "var(--color-green)", icon: CheckCircle, label: "Pass" },
  warn: { color: "var(--color-amber)", icon: AlertTriangle, label: "Warn" },
  fail: { color: "var(--color-red)",   icon: XCircle,      label: "Fail" },
  na:   { color: "var(--color-border-secondary)", icon: Clock, label: "N/A" },
};

function Compliance() {
  const qc = useQueryClient();
  const [eraseProjectId, setEraseProjectId] = useState("");
  const [eraseConfirm, setEraseConfirm] = useState(false);
  const [eraseResult, setEraseResult] = useState(null);
  const [purgeResult, setPurgeResult] = useState(null);
  const [form, setForm] = useState(null);

  const { data: report, isLoading, refetch } = useQuery({ queryKey: ["compliance-report"], queryFn: getComplianceReport, refetchInterval: 60000 });
  const { data: rbac } = useQuery({ queryKey: ["rbac-model"], queryFn: getRbacModel });
  const saveSettings = useMutation({ mutationFn: updateComplianceSettings, onSuccess: () => refetch() });
  const runPurge = useMutation({ mutationFn: runRetentionPurge, onSuccess: (data) => { setPurgeResult(data); refetch(); } });

  if (!form && report?.retention_settings) {
    const s = report.retention_settings;
    setForm({ raw_post_retention_days: s.raw_post_retention_days, enriched_post_retention_days: s.enriched_post_retention_days, audit_log_retention_days: s.audit_log_retention_days, auto_deletion_enabled: s.auto_deletion_enabled, gdpr_region: s.gdpr_region, hipaa_covered_entity: s.hipaa_covered_entity });
  }

  const runErase = async () => {
    if (!eraseProjectId.trim()) return;
    try {
      const result = await gdprErase({ project_id: eraseProjectId.trim(), requested_by: "admin" });
      setEraseResult(result); setEraseConfirm(false); refetch();
    } catch (e) { setEraseResult({ error: e?.response?.data?.detail || "Erasure failed" }); }
  };

  const stats = report?.stats;
  const checklist = report?.checklist || [];
  const passCount = checklist.filter((c) => c.status === "pass").length;
  const warnCount = checklist.filter((c) => c.status === "warn").length;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>Compliance & data governance</div>
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>GDPR · HIPAA · ICH E6 · FDA 21 CFR 314</div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <a href={`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/admin/compliance/audit-export?days=30`} target="_blank" rel="noreferrer"
            style={{ fontSize: 9, padding: "3px 8px", borderRadius: 4, border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-secondary)", color: "var(--color-text-secondary)", display: "flex", alignItems: "center", gap: 4, textDecoration: "none" }}>
            <Download size={10} /> Export CSV
          </a>
          <button onClick={() => refetch()} style={{ fontSize: 9, padding: "3px 8px", borderRadius: 4, border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-secondary)", color: "var(--color-text-secondary)", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
            <RefreshCw size={10} /> Refresh
          </button>
        </div>
      </div>

      {isLoading ? (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>Loading compliance report…</div>
      ) : (
        <>
          {/* Score summary */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 6, marginBottom: 14 }}>
            {[
              { label: "Controls passing", value: passCount, color: "var(--color-green)" },
              { label: "Warnings",          value: warnCount, color: "var(--color-amber)" },
              { label: "Posts with PII",    value: stats?.posts?.with_pii ?? "—", color: "var(--color-purple)" },
              { label: "Audit events 30d",  value: stats?.audit?.events_last_30d ?? "—", color: "var(--color-blue-text)" },
            ].map((c) => (
              <div key={c.label} style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 5, padding: "6px 10px" }}>
                <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 2 }}>{c.label}</div>
                <div style={{ fontSize: 18, fontWeight: 500, color: c.color }}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* Checklist */}
          <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, overflow: "hidden", marginBottom: 14 }}>
            {checklist.map((item, i) => {
              const s = CHECK_S[item.status] || CHECK_S.na;
              const Icon = s.icon;
              return (
                <div key={item.id} style={{ display: "flex", gap: 10, padding: "10px 12px", borderBottom: i < checklist.length - 1 ? "0.5px solid var(--color-border-tertiary)" : "none" }}>
                  <Icon size={13} color={s.color} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 2 }}>
                      <span style={{ fontSize: 11, fontWeight: 500 }}>{item.label}</span>
                      <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: `${s.color}20`, color: s.color, fontWeight: 600 }}>{s.label}</span>
                    </div>
                    <div style={{ fontSize: 9, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>{item.detail}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Retention form */}
          {form && (
            <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "12px 14px", marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 10 }}>Retention policy</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
                {[
                  ["Raw post retention (days)", "raw_post_retention_days"],
                  ["Enriched post retention (days)", "enriched_post_retention_days"],
                  ["Audit log retention (days)", "audit_log_retention_days"],
                  ["GDPR region", "gdpr_region", "text"],
                ].map(([label, key, type = "number"]) => (
                  <div key={key} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>{label}</div>
                    <input
                      type={type}
                      value={form[key] ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
                      style={{ width: "100%", background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 4, padding: "4px 7px", fontSize: 10, color: "var(--color-text-primary)", outline: "none" }}
                    />
                  </div>
                ))}
              </div>
              <button onClick={() => saveSettings.mutate(form)} style={{ fontSize: 10, padding: "4px 12px", borderRadius: 4, border: "0.5px solid var(--color-border-secondary)", background: "var(--color-background-secondary)", color: "var(--color-text-primary)", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                <Settings size={11} /> Save policy
              </button>
            </div>
          )}

          {/* Purge + Erase */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 14 }}>
            <button onClick={() => runPurge.mutate()} disabled={runPurge.isPending} style={{ fontSize: 10, padding: "4px 12px", borderRadius: 4, border: "0.5px solid var(--color-amber)", background: "var(--color-amber-bg)", color: "var(--color-amber-text)", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
              <Trash2 size={11} /> {runPurge.isPending ? "Running…" : "Run retention purge"}
            </button>
            {purgeResult && <span style={{ fontSize: 9, color: "var(--color-green)" }}>Purged at {new Date(purgeResult.ran_at).toLocaleString()}</span>}
          </div>

          {/* GDPR Erase */}
          <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-red)", borderRadius: 6, padding: "12px 14px", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <Lock size={12} color="var(--color-red)" />
              <span style={{ fontSize: 11, fontWeight: 500 }}>GDPR Art. 17 — Right to erasure</span>
            </div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", lineHeight: 1.6, marginBottom: 10 }}>
              Anonymises personal data in raw posts. Deidentified enriched posts and signals are preserved.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={eraseProjectId}
                onChange={(e) => { setEraseProjectId(e.target.value); setEraseConfirm(false); setEraseResult(null); }}
                placeholder="Project UUID"
                style={{ flex: 1, background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 4, padding: "4px 7px", fontSize: 10, color: "var(--color-text-primary)", outline: "none" }}
              />
              {!eraseConfirm ? (
                <button onClick={() => eraseProjectId.trim() && setEraseConfirm(true)} disabled={!eraseProjectId.trim()} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, border: "0.5px solid var(--color-red)", background: "var(--color-red-bg)", color: "var(--color-red-text)", cursor: "pointer" }}>
                  Erase PII
                </button>
              ) : (
                <div style={{ display: "flex", gap: 5 }}>
                  <button onClick={runErase} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, border: "none", background: "var(--color-red)", color: "#fff", cursor: "pointer", fontWeight: 600 }}>Confirm erase</button>
                  <button onClick={() => setEraseConfirm(false)} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, border: "0.5px solid var(--color-border-secondary)", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer" }}>Cancel</button>
                </div>
              )}
            </div>
            {eraseResult && (
              <div style={{ marginTop: 8, fontSize: 9, color: eraseResult.error ? "var(--color-red-text)" : "var(--color-green)" }}>
                {eraseResult.error ? `Error: ${eraseResult.error}` : `${eraseResult.erased_count} posts anonymised.`}
              </div>
            )}
          </div>

          {/* RBAC */}
          {rbac?.roles && (
            <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, overflow: "hidden" }}>
              <div style={{ padding: "8px 10px", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", alignItems: "center", gap: 6 }}>
                <Users size={12} color="var(--color-text-secondary)" />
                <span style={{ fontSize: 11, fontWeight: 500 }}>RBAC role model</span>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
                <thead>
                  <tr style={{ background: "var(--color-background-secondary)" }}>
                    {["Role", "Description", "Key permissions"].map((h) => (
                      <th key={h} style={{ padding: "6px 10px", textAlign: "left", fontSize: 9, fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(rbac.roles).map(([role, info]) => (
                    <tr key={role} style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
                      <td style={{ padding: "7px 10px" }}>
                        <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 2, background: role === "admin" ? "var(--color-red-bg)" : role === "regulatory" ? "var(--color-purple-bg)" : "var(--color-blue-bg)", color: role === "admin" ? "var(--color-red-text)" : role === "regulatory" ? "var(--color-purple-text)" : "var(--color-blue-text)" }}>
                          {role}
                        </span>
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--color-text-secondary)", maxWidth: 180, fontSize: 9 }}>{info.description}</td>
                      <td style={{ padding: "7px 10px" }}>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                          {(info.permissions || []).slice(0, 4).map((p) => (
                            <span key={p} style={{ fontSize: 8, padding: "1px 4px", borderRadius: 2, background: "var(--color-green-bg)", color: "var(--color-green-text)" }}>{p}</span>
                          ))}
                          {(info.permissions || []).length > 4 && <span style={{ fontSize: 8, color: "var(--color-text-secondary)" }}>+{info.permissions.length - 4}</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Main Admin page ───────────────────────────────────────────────────────────

import { Activity, Shield, ClipboardCheck, Eye, Lock as LockIcon } from "lucide-react";

const TABS = [
  { key: "health",     label: "Pipeline",     icon: Activity },
  { key: "discover",   label: "Discovery",    icon: Bot },
  { key: "signals",    label: "Sig. review",  icon: ClipboardCheck },
  { key: "pii",        label: "PII queue",    icon: Shield },
  { key: "compliance", label: "Compliance",   icon: LockIcon },
  { key: "audit",      label: "Audit log",    icon: Eye },
];

export default function Admin() {
  const [tab, setTab] = useState("health");

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 500 }}>Admin panel</span>
        <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
          Pipeline · Sources · PII · Compliance · Audit
        </span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
        {tab === "health"     && <PipelineHealth />}
        {tab === "discover"   && <SourceDiscovery />}
        {tab === "signals"    && <SignalReview />}
        {tab === "pii"        && <PIIReview />}
        {tab === "compliance" && <Compliance />}
        {tab === "audit"      && <AuditLog />}
      </div>
    </div>
  );
}
