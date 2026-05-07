import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getPipelineHealth, listPiiQueue, reviewPiiItem,
  discoverSources, getAuditLog, listSignalReview, getSignalReviewCounts,
  triageSignal, getComplianceReport, getComplianceSettings, updateComplianceSettings,
  runRetentionPurge, gdprErase, getRbacModel,
  listGlobalSources, addConfirmedSource, addCustomSource, toggleGlobalSource,
  deleteGlobalSource, probeApi,
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

const ACCESS_TYPE_COLOR = {
  rss: "var(--color-blue)",
  api: "var(--color-purple)",
  reddit: "var(--color-amber)",
};

function DiscoveredSourceCard({ src, added, onAdd, loading }) {
  const color = ACCESS_TYPE_COLOR[src.access_type] || "var(--color-border-secondary)";
  return (
    <div style={{
      background: "var(--color-background-primary)",
      border: `0.5px solid ${color}50`,
      borderRadius: 6, padding: "10px 12px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 2 }}>{src.name || src.domain}</div>
          <a href={src.url} target="_blank" rel="noreferrer" style={{ fontSize: 9, color: "var(--color-blue-text)", wordBreak: "break-all" }}>{src.url}</a>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
          {src.relevance_score && (
            <span style={{ fontSize: 9, fontWeight: 600, color: "var(--color-green)" }}>{Math.round(src.relevance_score * 100)}% match</span>
          )}
          {added ? (
            <span style={{ fontSize: 9, color: "var(--color-green)", display: "flex", alignItems: "center", gap: 3 }}>
              <CheckCircle size={10} /> Added to registry
            </span>
          ) : (
            <button
              onClick={onAdd}
              disabled={loading}
              style={{
                fontSize: 9, padding: "3px 8px", borderRadius: 3, cursor: loading ? "not-allowed" : "pointer",
                border: `0.5px solid ${color}`, background: `${color}15`, color,
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? "Adding…" : "Add to registry"}
            </button>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 8 }}>
        {src.access_type && (
          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 2, background: `${color}20`, color, fontWeight: 600 }}>
            {src.access_type.toUpperCase()}
          </span>
        )}
        <span style={{
          fontSize: 9, padding: "1px 5px", borderRadius: 2,
          background: src.supports_date_range ? "var(--color-green-bg)" : "var(--color-background-secondary)",
          color: src.supports_date_range ? "var(--color-green-text)" : "var(--color-text-secondary)",
        }}>
          {src.supports_date_range ? "⏱ timestamp filter" : "no date filter"}
        </span>
        {src.feed_url && (
          <span style={{ fontSize: 9, color: "var(--color-text-secondary)", wordBreak: "break-all" }}>
            feed: {src.feed_url.slice(0, 60)}{src.feed_url.length > 60 ? "…" : ""}
          </span>
        )}
      </div>

      {src.reason && (
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 6, lineHeight: 1.5 }}>{src.reason}</div>
      )}
    </div>
  );
}

function GlobalSourceRow({ gs, onToggle, onDelete }) {
  const TIER_C = { 1: "var(--color-green)", 2: "var(--color-blue)", 3: "var(--color-amber)", 4: "var(--color-red)" };
  const color = TIER_C[gs.reliability_tier] || "var(--color-border-secondary)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 10 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{gs.name}</span>
        <span style={{ color: "var(--color-text-secondary)", marginLeft: 6, fontSize: 9 }}>{gs.domain}</span>
      </div>
      <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: `${color}20`, color, fontWeight: 600, flexShrink: 0 }}>T{gs.reliability_tier}</span>
      <span style={{ fontSize: 9, flexShrink: 0, color: gs.supports_date_range ? "var(--color-green)" : "var(--color-text-secondary)" }}>
        {gs.supports_date_range ? "⏱ timestamp" : "no filter"}
      </span>
      <span style={{ fontSize: 9, color: "var(--color-text-secondary)", flexShrink: 0 }}>{gs.total_posts_pulled ?? 0} posts</span>
      <button
        onClick={() => onToggle(!gs.is_active)}
        style={{
          fontSize: 9, padding: "2px 6px", borderRadius: 3, cursor: "pointer", flexShrink: 0,
          border: `0.5px solid ${gs.is_active ? "var(--color-green)" : "var(--color-border-secondary)"}`,
          background: "transparent",
          color: gs.is_active ? "var(--color-green)" : "var(--color-text-secondary)",
        }}
      >
        {gs.is_active ? "Active" : "Disabled"}
      </button>
      <button
        onClick={() => {
          if (window.confirm(`Remove "${gs.name}" from the registry? This will unlink it from all projects.`)) {
            onDelete(gs.id);
          }
        }}
        title="Remove source"
        style={{
          fontSize: 9, padding: "2px 5px", borderRadius: 3, cursor: "pointer", flexShrink: 0,
          border: "0.5px solid var(--color-border-tertiary)", background: "transparent",
          color: "var(--color-red-text)", lineHeight: 1,
        }}
      >
        ✕
      </button>
    </div>
  );
}

function SourceDiscovery() {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState(null);
  const [addedDomains, setAddedDomains] = useState(new Set());
  const [showManual, setShowManual] = useState(false);
  const [showRegistry, setShowRegistry] = useState(true);
  const [manualForm, setManualForm] = useState({
    url: "", name: "", source_type: "rss", api_key: "", supports_date_range: false,
  });
  const [probedConfig, setProbedConfig] = useState(null); // detected API field mapping

  const { data: globalSources = [], refetch: refetchGlobal } = useQuery({
    queryKey: ["global-sources"],
    queryFn: listGlobalSources,
  });

  const discoverMut = useMutation({
    mutationFn: discoverSources,
    onSuccess: (data) => setResults(data),
  });

  const addConfirmedMut = useMutation({
    mutationFn: (src) => addConfirmedSource({
      name: src.name || src.domain,
      domain: src.domain,
      source_type: src.access_type || "rss",
      url: src.url,
      feed_url: src.feed_url || null,
      supports_date_range: src.supports_date_range || false,
    }),
    onSuccess: (saved) => {
      setAddedDomains((prev) => new Set([...prev, saved.domain]));
      refetchGlobal();
    },
  });

  const probeMut = useMutation({
    mutationFn: () => probeApi({ url: manualForm.url, api_key: manualForm.api_key || undefined }),
    onSuccess: (cfg) => {
      setProbedConfig(cfg);
      if (cfg.supports_date_range !== undefined) {
        setManualForm((f) => ({ ...f, supports_date_range: cfg.supports_date_range }));
      }
    },
  });

  const addCustomMut = useMutation({
    mutationFn: () => addCustomSource({
      url: manualForm.url,
      name: manualForm.name,
      source_type: manualForm.source_type,
      api_key: manualForm.api_key || undefined,
      scraper_config: manualForm.source_type === "api" ? probedConfig : undefined,
      supports_date_range: manualForm.supports_date_range,
    }),
    onSuccess: () => {
      refetchGlobal();
      setManualForm({ url: "", name: "", source_type: "rss", api_key: "", supports_date_range: false });
      setProbedConfig(null);
      setShowManual(false);
    },
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }) => toggleGlobalSource(id, enabled),
    onSuccess: () => refetchGlobal(),
  });

  const deleteMut = useMutation({
    mutationFn: (id) => deleteGlobalSource(id),
    onSuccess: () => refetchGlobal(),
  });

  const available = results?.available || [];
  const alreadyTracked = results?.already_tracked || [];
  const suggestions = results?.suggestions || [];
  const hasNewSource = available.length > 0;

  const inputStyle = {
    background: "var(--color-background-secondary)",
    border: "0.5px solid var(--color-border-tertiary)",
    borderRadius: 4, padding: "4px 8px",
    fontSize: 10, color: "var(--color-text-primary)", outline: "none",
  };

  return (
    <div style={{ maxWidth: 640 }}>
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Source discovery</div>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
          AI searches the web for new pharma data sources. Prototype: evaluates 1 extra source per run.
          Confirmed sources persist across all projects.
        </div>
      </div>

      {/* Search bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-secondary)", borderRadius: 5, padding: "6px 10px" }}>
          <Search size={12} color="var(--color-text-secondary)" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && keyword.trim() && discoverMut.mutate(keyword.trim())}
            placeholder="e.g. ozempic side effects forum…"
            style={{ flex: 1, background: "none", border: "none", outline: "none", fontSize: 11, color: "var(--color-text-primary)" }}
          />
        </div>
        <button
          onClick={() => keyword.trim() && discoverMut.mutate(keyword.trim())}
          disabled={!keyword.trim() || discoverMut.isPending}
          style={{
            padding: "6px 14px", borderRadius: 5, fontSize: 11, fontWeight: 500,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 5,
            opacity: !keyword.trim() || discoverMut.isPending ? 0.6 : 1,
          }}
        >
          <Bot size={12} /> {discoverMut.isPending ? "Searching…" : "Discover →"}
        </button>
      </div>

      {/* Loading state — discovery takes 15–30s, show progress so user knows it's working */}
      {discoverMut.isPending && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 14, padding: "10px 12px", background: "var(--color-background-secondary)", borderRadius: 5, display: "flex", alignItems: "center", gap: 8 }}>
          <RefreshCw size={11} style={{ animation: "spin 1.2s linear infinite" }} />
          <span>Searching the web and evaluating sources with AI — this takes 15–30 seconds…</span>
        </div>
      )}

      {/* Error state */}
      {discoverMut.isError && (
        <div style={{ fontSize: 10, color: "var(--color-red-text)", marginBottom: 14, padding: "8px 12px", background: "var(--color-background-secondary)", borderRadius: 5, border: "0.5px solid var(--color-red-text)" }}>
          Discovery failed: {discoverMut.error?.response?.data?.detail || discoverMut.error?.message || "Unknown error — check the backend logs."}
        </div>
      )}

      {/* Alert: new source found */}
      {hasNewSource && (
        <div style={{
          background: "var(--color-green-bg)", border: "0.5px solid var(--color-green)",
          borderRadius: 6, padding: "10px 14px", marginBottom: 14,
          display: "flex", gap: 8, alignItems: "flex-start",
        }}>
          <CheckCircle size={14} color="var(--color-green)" style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-green-text)", marginBottom: 2 }}>
              New source found — {available[0].name || available[0].domain}
            </div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>
              Prototype mode: 1 source surfaced per search. Add it to the reliable sources registry to activate it across all projects.
            </div>
          </div>
        </div>
      )}

      {/* Available sources */}
      {available.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, fontWeight: 500, marginBottom: 8, color: "var(--color-text-primary)" }}>
            Available ({available.length})
          </div>
          {available.map((src, i) => (
            <DiscoveredSourceCard
              key={i}
              src={src}
              added={addedDomains.has(src.domain)}
              loading={addConfirmedMut.isPending}
              onAdd={() => addConfirmedMut.mutate(src)}
            />
          ))}
        </div>
      )}

      {/* Already tracked */}
      {alreadyTracked.length > 0 && (
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 10, padding: "6px 10px", background: "var(--color-background-secondary)", borderRadius: 4 }}>
          Already in registry: {alreadyTracked.map((t) => t.domain).join(", ")}
        </div>
      )}

      {/* Suggestions (relevant but no free access) */}
      {suggestions.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, fontWeight: 500, marginBottom: 6, color: "var(--color-text-secondary)" }}>
            Relevant but no free access ({suggestions.length})
          </div>
          {suggestions.map((src, i) => (
            <div key={i} style={{
              display: "flex", justifyContent: "space-between", alignItems: "flex-start",
              padding: "6px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 10,
            }}>
              <div>
                <a href={src.url} target="_blank" rel="noreferrer" style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>
                  {src.name || src.domain}
                </a>
                <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 2 }}>{src.reason}</div>
              </div>
              <span style={{ fontSize: 9, color: "var(--color-text-secondary)", flexShrink: 0, marginLeft: 8 }}>
                {Math.round((src.relevance_score || 0) * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {/* No results state */}
      {results && !hasNewSource && suggestions.length === 0 && alreadyTracked.length === 0 && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", padding: "10px 0" }}>
          No new sources found for "{results.keyword}". Try a more specific keyword.
        </div>
      )}

      {/* Divider */}
      <div style={{ borderTop: "0.5px solid var(--color-border-tertiary)", margin: "16px 0" }} />

      {/* Manual add */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => setShowManual(!showManual)}
          style={{
            fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
            border: "0.5px solid var(--color-border-secondary)",
            background: "transparent", color: "var(--color-text-secondary)",
            display: "flex", alignItems: "center", gap: 5,
          }}
        >
          + Add source manually (API key / feed URL)
        </button>

        {showManual && (
          <div style={{ marginTop: 10, padding: "12px", background: "var(--color-background-secondary)", borderRadius: 6, border: "0.5px solid var(--color-border-tertiary)" }}>
            {/* Type tabs */}
            <div style={{ display: "flex", gap: 2, marginBottom: 12 }}>
              {["rss", "api"].map((t) => (
                <button key={t} onClick={() => { setManualForm((f) => ({ ...f, source_type: t })); setProbedConfig(null); }} style={{
                  fontSize: 10, padding: "3px 10px", borderRadius: 3, cursor: "pointer",
                  border: `0.5px solid ${manualForm.source_type === t ? "var(--color-border-primary)" : "var(--color-border-tertiary)"}`,
                  background: manualForm.source_type === t ? "var(--color-background-primary)" : "transparent",
                  color: manualForm.source_type === t ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                  fontWeight: manualForm.source_type === t ? 500 : 400,
                }}>
                  {t === "rss" ? "RSS Feed" : "JSON API"}
                </button>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 12px", marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>
                  {manualForm.source_type === "rss" ? "Feed URL *" : "API fetch URL * (use {keyword}, {limit}, {since_iso})"}
                </div>
                <input
                  value={manualForm.url}
                  onChange={(e) => { setManualForm((f) => ({ ...f, url: e.target.value })); setProbedConfig(null); }}
                  placeholder={manualForm.source_type === "rss" ? "https://example.com/rss?q={keyword}" : "https://api.example.com/posts?q={keyword}&limit={limit}"}
                  style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
                />
              </div>
              <div>
                <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>Display name *</div>
                <input
                  value={manualForm.name}
                  onChange={(e) => setManualForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Patient Forum — Example"
                  style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
                />
              </div>
              {manualForm.source_type === "api" && (
                <div style={{ gridColumn: "span 2" }}>
                  <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>API key (optional — Bearer token)</div>
                  <input
                    value={manualForm.api_key}
                    onChange={(e) => { setManualForm((f) => ({ ...f, api_key: e.target.value })); setProbedConfig(null); }}
                    placeholder="sk-…"
                    type="password"
                    style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
                  />
                </div>
              )}
            </div>

            {/* API: auto-detect button + detected fields */}
            {manualForm.source_type === "api" && (
              <div style={{ marginBottom: 10 }}>
                <button
                  onClick={() => probeMut.mutate()}
                  disabled={!manualForm.url || probeMut.isPending}
                  style={{
                    fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                    border: "0.5px solid var(--color-blue)", background: "transparent",
                    color: "var(--color-blue)", opacity: !manualForm.url ? 0.5 : 1,
                  }}
                >
                  {probeMut.isPending ? "Detecting fields…" : "⚡ Auto-detect response fields"}
                </button>
                {probeMut.isError && (
                  <div style={{ fontSize: 9, color: "var(--color-red-text)", marginTop: 4 }}>
                    {probeMut.error?.response?.data?.detail || "Could not reach the API URL."}
                  </div>
                )}
                {probedConfig && (
                  <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--color-background-primary)", borderRadius: 4, border: "0.5px solid var(--color-border-tertiary)" }}>
                    <div style={{ fontSize: 9, fontWeight: 500, marginBottom: 6, color: "var(--color-green-text)" }}>
                      Fields detected — confirm before adding:
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {["items_path", "text_field", "title_field", "author_field", "url_field", "id_field", "date_field"].map((key) => (
                        probedConfig[key] ? (
                          <span key={key} style={{
                            fontSize: 9, padding: "2px 6px", borderRadius: 3,
                            background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-secondary)",
                            color: "var(--color-text-secondary)",
                          }}>
                            <span style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>{key.replace("_field", "").replace("_path", " path")}</span>: {probedConfig[key]}
                          </span>
                        ) : null
                      ))}
                    </div>
                    {probedConfig._note && (
                      <div style={{ fontSize: 9, color: "var(--color-amber)", marginTop: 6 }}>{probedConfig._note}</div>
                    )}
                  </div>
                )}
              </div>
            )}

            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 10, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={manualForm.supports_date_range}
                onChange={(e) => setManualForm((f) => ({ ...f, supports_date_range: e.target.checked }))}
              />
              Source supports server-side date range filtering (e.g. ?since=, ?from=, ?start_date=)
            </label>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={() => addCustomMut.mutate()}
                disabled={!manualForm.url || !manualForm.name || addCustomMut.isPending || (manualForm.source_type === "api" && !probedConfig)}
                style={{
                  fontSize: 10, padding: "4px 12px", borderRadius: 4, cursor: "pointer",
                  border: "0.5px solid var(--color-border-primary)",
                  background: "var(--color-background-primary)",
                  color: "var(--color-text-primary)",
                  opacity: (!manualForm.url || !manualForm.name || (manualForm.source_type === "api" && !probedConfig)) ? 0.5 : 1,
                }}
              >
                {addCustomMut.isPending ? "Adding…" : "Add to registry"}
              </button>
              <button
                onClick={() => { setShowManual(false); setProbedConfig(null); }}
                style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer", border: "0.5px solid var(--color-border-tertiary)", background: "transparent", color: "var(--color-text-secondary)" }}
              >
                Cancel
              </button>
            </div>
            {manualForm.source_type === "api" && !probedConfig && manualForm.url && (
              <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 6 }}>
                Click "Auto-detect response fields" first so the scraper knows how to parse the API response.
              </div>
            )}
            {addCustomMut.isError && (
              <div style={{ fontSize: 9, color: "var(--color-red-text)", marginTop: 6 }}>
                {addCustomMut.error?.response?.data?.detail || "Failed to add source — check the URL and try again."}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Reliable sources registry */}
      <div>
        <div
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, cursor: "pointer" }}
          onClick={() => setShowRegistry(!showRegistry)}
        >
          <div style={{ fontSize: 11, fontWeight: 500 }}>
            Reliable sources registry
            <span style={{ fontSize: 9, color: "var(--color-text-secondary)", marginLeft: 6, fontWeight: 400 }}>
              {globalSources.length} sources — available across all projects
            </span>
          </div>
          <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>{showRegistry ? "▲" : "▼"}</span>
        </div>

        {showRegistry && (
          globalSources.length === 0 ? (
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", padding: "10px 0" }}>No sources in registry yet.</div>
          ) : (
            <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "0 10px" }}>
              {globalSources.map((gs) => (
                <GlobalSourceRow
                  key={gs.id}
                  gs={gs}
                  onToggle={(enabled) => toggleMut.mutate({ id: gs.id, enabled })}
                  onDelete={(id) => deleteMut.mutate(id)}
                />
              ))}
            </div>
          )
        )}
      </div>
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
