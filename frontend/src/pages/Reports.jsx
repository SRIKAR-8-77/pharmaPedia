import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, ExternalLink, RefreshCw } from "lucide-react";
import api from "../api/client";

const listReports = (projectId) =>
  api.get(`/projects/${projectId}/reports`).then((r) => r.data);

const generateReport = (projectId, days) =>
  api.post(`/projects/${projectId}/reports?days=${days}`).then((r) => r.data);

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SEV_COLOR = {
  HIGH: "var(--color-red-text)",
  MED:  "var(--color-amber-text)",
  LOW:  "var(--color-green-text)",
};

function StatPill({ label, value, color }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 18, fontWeight: 600, color: color || "var(--color-text-primary)" }}>{value ?? "—"}</div>
      <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>{label}</div>
    </div>
  );
}

function ReportCard({ report, projectId }) {
  const start   = new Date(report.period_start).toLocaleDateString();
  const end     = new Date(report.period_end).toLocaleDateString();
  const created = new Date(report.created_at).toLocaleString();
  const content = report.content || {};
  const sigs    = content.signal_summary || {};

  return (
    <div style={{
      background: "var(--color-background-primary)",
      border: "0.5px solid var(--color-border-tertiary)",
      borderRadius: 6, padding: "10px 12px", marginBottom: 8,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>{content.title || "PV Report"}</div>
          <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
            {start} → {end} · Generated {created}
          </div>
        </div>
        <a
          href={`${BASE_URL}/projects/${projectId}/reports/${report.id}/html`}
          target="_blank"
          rel="noreferrer"
          style={{
            display: "flex", alignItems: "center", gap: 4, fontSize: 9, padding: "3px 8px", borderRadius: 4,
            border: "0.5px solid var(--color-blue)", background: "var(--color-blue-bg)",
            color: "var(--color-blue-text)", textDecoration: "none",
          }}
        >
          <ExternalLink size={10} /> View / Print PDF
        </a>
      </div>

      {/* Signal summary */}
      <div style={{ display: "flex", gap: 20, padding: "8px 0", borderTop: "0.5px solid var(--color-border-tertiary)", borderBottom: "0.5px solid var(--color-border-tertiary)", marginBottom: 8, flexWrap: "wrap" }}>
        <StatPill label="HIGH" value={sigs.HIGH} color="var(--color-red-text)" />
        <StatPill label="MED"  value={sigs.MED}  color="var(--color-amber-text)" />
        <StatPill label="LOW"  value={sigs.LOW}  color="var(--color-green-text)" />
        <StatPill label="Novel" value={sigs.novel_signals} color="var(--color-purple)" />
        <StatPill label="Escalated" value={sigs.escalated} color="var(--color-red-text)" />
      </div>

      {/* Executive summary */}
      {content.executive_summary && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", lineHeight: 1.6, marginBottom: 8, borderLeft: "2px solid var(--color-border-secondary)", paddingLeft: 8 }}>
          {content.executive_summary}
        </div>
      )}

      {/* Recommendations */}
      {content.recommendations?.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 9, fontWeight: 600, color: "var(--color-text-secondary)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Recommendations
          </div>
          {content.recommendations.map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 3, fontSize: 10 }}>
              <span style={{ color: SEV_COLOR[r.priority] || "var(--color-text-secondary)", fontWeight: 600, flexShrink: 0 }}>
                [{r.priority}]
              </span>
              <span style={{ color: "var(--color-text-secondary)" }}>{r.action}</span>
            </div>
          ))}
        </div>
      )}

      {/* Top signals */}
      {content.top_signals?.length > 0 && (
        <details>
          <summary style={{ fontSize: 10, fontWeight: 500, cursor: "pointer", color: "var(--color-text-secondary)", marginBottom: 4 }}>
            Top {content.top_signals.length} signals ▾
          </summary>
          <div style={{ overflowX: "auto", marginTop: 6 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
              <thead>
                <tr style={{ background: "var(--color-background-secondary)" }}>
                  {["Drug", "Symptom", "Sev", "Conf", "MedDRA", "FDA"].map((h) => (
                    <th key={h} style={{ padding: "4px 8px", textAlign: "left", color: "var(--color-text-secondary)", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {content.top_signals.map((s, i) => (
                  <tr key={i} style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
                    <td style={{ padding: "5px 8px", fontWeight: 500 }}>{s.drug}</td>
                    <td style={{ padding: "5px 8px" }}>{s.symptom}</td>
                    <td style={{ padding: "5px 8px", color: SEV_COLOR[s.severity], fontWeight: 600 }}>{s.severity}</td>
                    <td style={{ padding: "5px 8px" }}>{Math.round((s.confidence || 0) * 100)}%</td>
                    <td style={{ padding: "5px 8px", color: "var(--color-purple)" }}>{s.meddra_term || "—"}</td>
                    <td style={{ padding: "5px 8px" }}>
                      {s.known_to_fda === true && <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 2, background: "var(--color-green-bg)", color: "var(--color-green-text)", fontWeight: 600 }}>Known</span>}
                      {s.known_to_fda === false && <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 2, background: "var(--color-red-bg)", color: "var(--color-red-text)", fontWeight: 600 }}>Novel</span>}
                      {s.known_to_fda == null && <span style={{ color: "var(--color-text-secondary)" }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

export default function Reports() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);
  const [generating, setGenerating] = useState(false);

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
    enabled: !!projectId,
  });

  const generate = async () => {
    setGenerating(true);
    try {
      await generateReport(projectId, days);
      qc.invalidateQueries(["reports", projectId]);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>PV Reports</span>

        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{
          fontSize: 10, padding: "3px 6px", borderRadius: 4,
          border: "0.5px solid var(--color-border-secondary)",
          background: "var(--color-background-secondary)", color: "var(--color-text-primary)", cursor: "pointer",
        }}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={180}>Last 6 months</option>
          <option value={365}>Last 12 months</option>
        </select>

        <button onClick={generate} disabled={generating} style={{
          fontSize: 10, padding: "3px 10px", borderRadius: 4,
          border: "0.5px solid var(--color-border-secondary)",
          background: "var(--color-background-secondary)",
          color: "var(--color-text-primary)", fontWeight: 500, cursor: generating ? "not-allowed" : "pointer",
          display: "flex", alignItems: "center", gap: 4,
          opacity: generating ? 0.6 : 1,
        }}>
          <RefreshCw size={10} /> {generating ? "Generating…" : "Generate report"}
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 10 }}>
          Structured PV reports. Open in new tab and use Ctrl+P to save as PDF.
        </div>

        {isLoading ? (
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>Loading reports…</div>
        ) : reports.length === 0 ? (
          <div style={{ border: "0.5px dashed var(--color-border-secondary)", borderRadius: 6, padding: "40px", textAlign: "center" }}>
            <FileText size={24} color="var(--color-text-secondary)" style={{ marginBottom: 8 }} />
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 4 }}>No reports yet.</div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>Click "Generate report" to create your first pharmacovigilance report.</div>
          </div>
        ) : (
          reports.map((r) => <ReportCard key={r.id} report={r} projectId={projectId} />)
        )}
      </div>
    </div>
  );
}
