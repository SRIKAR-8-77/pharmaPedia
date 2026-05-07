import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDashboardStats, getProject, listSignals, getProjectSources, triggerScrape, runPipeline, pauseProject, resumeProject } from "../api/client";
import { RefreshCw, Zap, PauseCircle, PlayCircle } from "lucide-react";
import toast from "react-hot-toast";

const SEV_STYLE = {
  HIGH: { bg: "var(--color-red-bg)",   color: "var(--color-red-text)" },
  MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)" },
  LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)" },
};

// ── Compact metric card ───────────────────────────────────────────────────────

function MetricCard({ label, value, sub, valueColor }) {
  return (
    <div style={{
      background: "var(--color-background-secondary)",
      borderRadius: 6, padding: "8px 10px",
    }}>
      <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>{label}</div>
      <div style={{
        fontSize: 18, fontWeight: 500,
        color: valueColor || "var(--color-text-primary)",
      }}>{value}</div>
      {sub && <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

// ── Horizontal bar chart row ──────────────────────────────────────────────────

function BarRow({ label, value, max, fillColor }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3 }}>
      <span style={{ fontSize: 9, color: "var(--color-text-secondary)", width: 48, textAlign: "right", flexShrink: 0 }}>
        {label}
      </span>
      <div style={{
        flex: 1, height: 5,
        background: "var(--color-background-secondary)",
        borderRadius: 3, overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: fillColor, borderRadius: 3,
          transition: "width 0.4s ease",
        }} />
      </div>
      <span style={{ fontSize: 9, color: "var(--color-text-secondary)", width: 24 }}>{value}</span>
    </div>
  );
}

// ── Signal feed item ──────────────────────────────────────────────────────────

function SignalItem({ sig, onNavigate }) {
  const sev = SEV_STYLE[sig.severity] || SEV_STYLE.LOW;
  return (
    <div style={{
      display: "flex", gap: 8, padding: "7px 0",
      borderBottom: "0.5px solid var(--color-border-tertiary)",
      alignItems: "flex-start",
    }}>
      <span style={{
        fontSize: 9, padding: "2px 5px", borderRadius: 3, fontWeight: 500,
        flexShrink: 0, marginTop: 1,
        background: sev.bg, color: sev.color,
      }}>{sig.severity}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 10, color: "var(--color-text-primary)", lineHeight: 1.4 }}>
          {sig.context_window}
        </div>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 2, display: "flex", gap: 4, flexWrap: "wrap" }}>
          {sig.drug && (
            <span style={{ display: "inline-block", fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-blue-bg)", color: "var(--color-blue-text)" }}>
              {sig.drug}
            </span>
          )}
          {sig.symptom && (
            <span style={{ display: "inline-block", fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-amber-bg)", color: "var(--color-amber-text)" }}>
              {sig.symptom}
            </span>
          )}
          <span>Conf {((sig.confidence || 0) * 100).toFixed(0)}%</span>
          <span>·</span>
          <span>{new Date(sig.created_at).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  );
}

// ── Pipeline status panel ─────────────────────────────────────────────────────

const STATUS_DOT = {
  active:   "var(--color-green)",
  healthy:  "var(--color-green)",
  degraded: "var(--color-amber)",
  healing:  "var(--color-amber)",
  error:    "var(--color-red)",
  paused:   "var(--color-border-secondary)",
  pending:  "var(--color-border-secondary)",
};

function PipelineStatus({ projectId, isPaused }) {
  const qc = useQueryClient();

  const { data: sources = [], isFetching } = useQuery({
    queryKey: ["project-sources", projectId],
    queryFn: () => getProjectSources(projectId),
    refetchInterval: 10000,
  });

  const scrapeMut = useMutation({
    mutationFn: () => triggerScrape(projectId),
    onSuccess: () => {
      toast.success("Scrape job queued — sources are being polled");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["project-sources", projectId] }), 4000);
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "Failed to queue scrape"),
  });

  const pipelineMut = useMutation({
    mutationFn: () => runPipeline(projectId),
    onSuccess: () => {
      toast.success("NLP pipeline started — posts are being enriched");
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["stats", projectId] });
        qc.invalidateQueries({ queryKey: ["signals-high", projectId] });
      }, 6000);
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "Failed to start pipeline"),
  });

  const pauseMut = useMutation({
    mutationFn: () => isPaused ? resumeProject(projectId) : pauseProject(projectId),
    onSuccess: () => {
      toast.success(isPaused ? "Jobs resumed — scraping and pipeline will run again" : "Jobs paused — no new data will be fetched");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "Failed to update project"),
  });

  const fmtTime = (iso) => {
    if (!iso) return "never";
    const d = new Date(iso);
    const diffMin = Math.round((Date.now() - d) / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleDateString();
  };

  return (
    <div style={{
      background: "var(--color-background-primary)",
      border: "0.5px solid var(--color-border-tertiary)",
      borderRadius: 6, padding: "8px 10px", marginBottom: 8,
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", flex: 1 }}>
          Pipeline status
          {isPaused && (
            <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "var(--color-amber-bg)", color: "var(--color-amber-text)", fontWeight: 600, letterSpacing: "0.04em" }}>
              PAUSED
            </span>
          )}
          {isFetching && (
            <RefreshCw size={9} style={{ animation: "spin 1.2s linear infinite", opacity: 0.4 }} />
          )}
        </span>
        <button
          onClick={() => pauseMut.mutate()}
          disabled={pauseMut.isPending}
          title={isPaused ? "Resume scraping and pipeline jobs" : "Pause all scraping and pipeline jobs"}
          style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 3, cursor: "pointer",
            border: isPaused ? "0.5px solid var(--color-green-text)" : "0.5px solid var(--color-amber-text)",
            background: "transparent",
            color: isPaused ? "var(--color-green-text)" : "var(--color-amber-text)",
            display: "flex", alignItems: "center", gap: 3,
            opacity: pauseMut.isPending ? 0.5 : 1,
          }}
        >
          {isPaused
            ? <><PlayCircle size={9} /> {pauseMut.isPending ? "Resuming…" : "Resume jobs"}</>
            : <><PauseCircle size={9} /> {pauseMut.isPending ? "Pausing…" : "Pause jobs"}</>
          }
        </button>
        <button
          onClick={() => scrapeMut.mutate()}
          disabled={scrapeMut.isPending || isPaused}
          title={isPaused ? "Resume jobs first" : "Pull new posts from all sources now"}
          style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 3, cursor: isPaused ? "not-allowed" : "pointer",
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-secondary)",
            display: "flex", alignItems: "center", gap: 3,
            opacity: (scrapeMut.isPending || isPaused) ? 0.4 : 1,
          }}
        >
          <RefreshCw size={9} /> {scrapeMut.isPending ? "Queuing…" : "Scrape now"}
        </button>
        <button
          onClick={() => pipelineMut.mutate()}
          disabled={pipelineMut.isPending || isPaused}
          title={isPaused ? "Resume jobs first" : "Run NLP pipeline on unprocessed posts"}
          style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 3, cursor: isPaused ? "not-allowed" : "pointer",
            border: "0.5px solid var(--color-purple)",
            background: "transparent",
            color: "var(--color-purple)",
            display: "flex", alignItems: "center", gap: 3,
            opacity: (pipelineMut.isPending || isPaused) ? 0.4 : 1,
          }}
        >
          <Zap size={9} /> {pipelineMut.isPending ? "Running…" : "Run pipeline"}
        </button>
      </div>

      {/* Source rows */}
      {sources.length === 0 ? (
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>No sources linked to this project yet.</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
          <thead>
            <tr>
              {["Source", "Status", "Last run", "Posts/hr", "Errors"].map((h) => (
                <th key={h} style={{
                  textAlign: "left", padding: "0 6px 4px 0",
                  color: "var(--color-text-secondary)", fontWeight: 500,
                  textTransform: "uppercase", letterSpacing: "0.04em", fontSize: 8,
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id} style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
                <td style={{ padding: "5px 6px 5px 0", fontWeight: 500, color: "var(--color-text-primary)" }}>
                  {s.name}
                </td>
                <td style={{ padding: "5px 6px 5px 0" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: STATUS_DOT[s.status] || STATUS_DOT.paused, display: "inline-block" }} />
                    {s.status}
                  </span>
                </td>
                <td style={{ padding: "5px 6px 5px 0", color: "var(--color-text-secondary)" }}>
                  {fmtTime(s.last_run)}
                </td>
                <td style={{ padding: "5px 6px 5px 0", color: "var(--color-text-secondary)" }}>
                  {s.posts_per_hour > 0 ? s.posts_per_hour.toFixed(1) : "—"}
                </td>
                <td style={{ padding: "5px 0", color: s.error_count > 0 ? "var(--color-red-text)" : "var(--color-text-secondary)" }}>
                  {s.error_count > 0 ? `⚠ ${s.error_count}` : "0"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });

  const { data: stats } = useQuery({
    queryKey: ["stats", projectId],
    queryFn: () => getDashboardStats(projectId),
    refetchInterval: 30000,
  });

  const { data: highSignals } = useQuery({
    queryKey: ["signals-high", projectId],
    queryFn: () => listSignals(projectId, { severity: "HIGH", page_size: 5 }),
    refetchInterval: 30000,
  });

  /* Mention volume bars */
  const volumeRows = stats?.mention_volume_7d || [];
  const maxVol = Math.max(...volumeRows.map((d) => d.count), 1);

  /* Symptom bars — top_symptoms from stats or derived from signals */
  const symptomRows = stats?.top_symptoms || [];
  const maxSym = Math.max(...symptomRows.map((s) => s.count), 1);

  const sentimentStr = stats?.avg_sentiment != null
    ? stats.avg_sentiment.toFixed(2)
    : "—";

  const piiPending = stats?.pii_queue_depth ?? "—";

  /* Color scale for volume bars */
  const volumeColors = ["#b5d4f4", "#b5d4f4", "#85b7eb", "#85b7eb", "#85b7eb", "#378add", "#378add"];

  /* Severity-based symptom color */
  const symColor = (i) => {
    if (i < 2) return "#ef9f27";
    if (i < 5) return "#fac775";
    return "#e24b4a";
  };

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)",
        flexShrink: 0,
        background: "var(--color-background-primary)",
      }}>
        <span style={{ fontSize: 12, fontWeight: 500, flex: 1, color: "var(--color-text-primary)" }}>
          {project?.name || "Overview"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>
          {project?.keywords?.slice(0, 3).join(", ")}
        </span>
        <button
          onClick={() => navigate(`/projects/${projectId}/signals`)}
          style={{
            fontSize: 10, padding: "3px 8px", borderRadius: 4,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)", cursor: "pointer",
          }}
        >
          View Signals
        </button>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>

        {/* Pipeline status */}
        <PipelineStatus projectId={projectId} isPaused={project?.is_paused ?? false} />

        {/* Metric cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 6, marginBottom: 10 }}>
          <MetricCard
            label="Posts collected"
            value={stats?.total_posts?.toLocaleString() ?? "—"}
            sub={`↑ ${stats?.posts_today ?? 0} today`}
          />
          <MetricCard
            label="Safety signals"
            value={stats?.signal_counts?.HIGH ?? "—"}
            sub={`${stats?.signal_counts?.MED ?? 0} MED · ${stats?.signal_counts?.LOW ?? 0} LOW`}
            valueColor="var(--color-red-text)"
          />
          <MetricCard
            label="Avg sentiment"
            value={sentimentStr}
            sub={
              stats?.avg_sentiment != null
                ? stats.avg_sentiment > 0.05 ? "Positive" : stats.avg_sentiment < -0.05 ? "Slightly negative" : "Neutral"
                : undefined
            }
          />
          <MetricCard
            label="PII flagged"
            value={piiPending}
            sub="Pending review"
          />
        </div>

        {/* Chart row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>

          {/* Mention volume */}
          <div style={{
            background: "var(--color-background-primary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: 6, padding: "8px 10px",
          }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", marginBottom: 6 }}>
              Mention volume — last 7 days
            </div>
            {volumeRows.length > 0 ? (
              volumeRows.map((d, i) => (
                <BarRow
                  key={d.date}
                  label={d.date.slice(5)}
                  value={d.count}
                  max={maxVol}
                  fillColor={volumeColors[Math.min(i, volumeColors.length - 1)]}
                />
              ))
            ) : (
              <div style={{ fontSize: 9, color: "var(--color-text-secondary)", padding: "8px 0" }}>No data yet</div>
            )}
          </div>

          {/* Top reported symptoms */}
          <div style={{
            background: "var(--color-background-primary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: 6, padding: "8px 10px",
          }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)", marginBottom: 6 }}>
              Top reported symptoms
            </div>
            {symptomRows.length > 0 ? (
              symptomRows.slice(0, 7).map((s, i) => (
                <BarRow
                  key={s.symptom}
                  label={s.symptom}
                  value={s.count}
                  max={maxSym}
                  fillColor={symColor(i)}
                />
              ))
            ) : (
              <div style={{ fontSize: 9, color: "var(--color-text-secondary)", padding: "8px 0" }}>No symptom data yet</div>
            )}
          </div>
        </div>

        {/* Recent HIGH signals */}
        <div style={{
          background: "var(--color-background-primary)",
          border: "0.5px solid var(--color-border-tertiary)",
          borderRadius: 6, padding: "8px 10px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-secondary)" }}>
              Recent HIGH signals
            </span>
            <button
              onClick={() => navigate(`/projects/${projectId}/signals`)}
              style={{
                fontSize: 9, background: "none", border: "none",
                color: "var(--color-purple)", cursor: "pointer",
              }}
            >
              View all →
            </button>
          </div>

          {!highSignals?.items?.length ? (
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", padding: "8px 0" }}>
              No HIGH signals yet. Run the pipeline to process posts.
            </div>
          ) : (
            highSignals.items.map((sig) => (
              <SignalItem key={sig.id} sig={sig} onNavigate={() => navigate(`/projects/${projectId}/signals`)} />
            ))
          )}
        </div>

      </div>
    </div>
  );
}
