import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listSignals, triageSignal, triageSignalWithAI } from "../api/client";
import { Search, AlertTriangle } from "lucide-react";

const SEV_STYLE = {
  HIGH: { bg: "var(--color-red-bg)",   color: "var(--color-red-text)"   },
  MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)" },
  LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)" },
};

const TRIAGE_OPTS = ["pending", "escalate", "monitor", "dismiss"];

// ── Signal item (compact feed style) ─────────────────────────────────────────

function SignalItem({ signal, onTriage, onTriageAI, isAILoading }) {
  const sev = SEV_STYLE[signal.severity] || SEV_STYLE.LOW;

  return (
    <div style={{
      display: "flex", gap: 8, padding: "7px 0",
      borderBottom: "0.5px solid var(--color-border-tertiary)",
      alignItems: "flex-start",
    }}>
      {/* Severity badge */}
      <span style={{
        fontSize: 9, padding: "2px 5px", borderRadius: 3, fontWeight: 500,
        flexShrink: 0, marginTop: 1,
        background: sev.bg, color: sev.color,
      }}>{signal.severity}</span>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Post excerpt */}
        <div style={{ fontSize: 10, color: "var(--color-text-primary)", lineHeight: 1.4, marginBottom: 2 }}>
          {signal.context_window}
        </div>

        {/* Meta line */}
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>
          {signal.causality && `${signal.causality} · `}
          Conf {((signal.confidence || 0) * 100).toFixed(0)}%
          {signal.created_at && ` · ${new Date(signal.created_at).toLocaleDateString()}`}
        </div>

        {/* Entity tags */}
        <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginBottom: 4 }}>
          {signal.drug && (
            <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-blue-bg)", color: "var(--color-blue-text)" }}>
              {signal.drug}
            </span>
          )}
          {signal.symptom && (
            <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-amber-bg)", color: "var(--color-amber-text)" }}>
              {signal.symptom}
            </span>
          )}
          {signal.meddra_term && (
            <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-green-bg)", color: "var(--color-green-text)" }}>
              {signal.meddra_term}
            </span>
          )}
          {signal.triage_ai_result?.fda_known === false && (
            <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, background: "var(--color-red-bg)", color: "var(--color-red-text)", fontWeight: 600 }}>
              ★ Novel
            </span>
          )}
        </div>

        {/* AI rationale */}
        {signal.triage_ai_result && (
          <div style={{
            fontSize: 9, lineHeight: 1.4, padding: "4px 6px", borderRadius: 4,
            background: "var(--color-purple-bg)", color: "var(--color-purple-text)",
            marginBottom: 4,
          }}>
            {typeof signal.triage_ai_result === "string"
              ? signal.triage_ai_result
              : JSON.stringify(signal.triage_ai_result)}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
          <button
            onClick={onTriageAI}
            disabled={isAILoading}
            style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 3,
              border: `0.5px solid var(--color-purple)`,
              background: "transparent", color: "var(--color-purple)",
              cursor: isAILoading ? "not-allowed" : "pointer",
              opacity: isAILoading ? 0.6 : 1,
            }}
          >
            {isAILoading ? "Analyzing…" : "Triage via AI"}
          </button>
          <button
            onClick={() => onTriage("escalate")}
            style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 3,
              border: `0.5px solid var(--color-green)`,
              background: "transparent", color: "var(--color-green)",
              cursor: "pointer",
            }}
          >
            Escalate
          </button>
          <button
            onClick={() => onTriage("monitor")}
            style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 3,
              border: "0.5px solid var(--color-border-secondary)",
              background: "transparent", color: "var(--color-text-secondary)",
              cursor: "pointer",
            }}
          >
            Monitor
          </button>
          <button
            onClick={() => onTriage("dismiss")}
            style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 3,
              border: `0.5px solid var(--color-red)`,
              background: "transparent", color: "var(--color-red-text)",
              cursor: "pointer",
            }}
          >
            Dismiss
          </button>
          <select
            value={signal.triage_action || "pending"}
            onChange={(e) => onTriage(e.target.value)}
            style={{
              marginLeft: 4, fontSize: 9, padding: "2px 4px",
              border: "0.5px solid var(--color-border-secondary)",
              borderRadius: 3, background: "var(--color-background-secondary)",
              color: "var(--color-text-secondary)", cursor: "pointer",
            }}
          >
            {TRIAGE_OPTS.map((o) => (
              <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

const SEV_TABS = ["ALL", "HIGH", "MED", "LOW"];

export default function Signals() {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const [tab, setTab] = useState("ALL");
  const [page, setPage] = useState(1);
  const [drugFilter, setDrugFilter] = useState("");
  const [aiLoadingId, setAILoadingId] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["signals", projectId, tab, page, drugFilter],
    queryFn: () => listSignals(projectId, {
      severity: tab === "ALL" ? undefined : tab,
      drug: drugFilter || undefined,
      page, page_size: 15,
    }),
    keepPreviousData: true,
  });

  const triage = useMutation({
    mutationFn: ({ id, action }) => triageSignal(id, { triage_action: action, triage_rationale: "" }),
    onSuccess: () => qc.invalidateQueries(["signals", projectId]),
  });

  const triageAI = useMutation({
    mutationFn: (id) => triageSignalWithAI(id),
    onSuccess: () => qc.invalidateQueries(["signals", projectId]),
  });

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 1;

  const tabColor = (t) => {
    if (t === "HIGH") return "var(--color-red-text)";
    if (t === "MED")  return "var(--color-amber-text)";
    if (t === "LOW")  return "var(--color-green-text)";
    return "var(--color-text-primary)";
  };

  const tabBg = (t) => {
    if (t === "HIGH") return "var(--color-red-bg)";
    if (t === "MED")  return "var(--color-amber-bg)";
    if (t === "LOW")  return "var(--color-green-bg)";
    return "var(--color-background-secondary)";
  };

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 6, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
        background: "var(--color-background-primary)",
      }}>
        <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>Safety signals</span>

        {/* Severity filter tabs */}
        {SEV_TABS.map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setPage(1); }}
            style={{
              fontSize: 10, padding: "3px 8px", borderRadius: 4,
              border: "0.5px solid " + (tab === t ? "var(--color-border-primary)" : "var(--color-border-secondary)"),
              background: tab === t ? tabBg(t) : "transparent",
              color: tab === t ? tabColor(t) : "var(--color-text-secondary)",
              fontWeight: tab === t ? 500 : 400,
              cursor: "pointer",
            }}
          >
            {t === "ALL" ? `All (${total})` : `${t}: ${data?.counts?.[t] ?? "—"}`}
          </button>
        ))}

        {/* Drug filter */}
        <div style={{
          display: "flex", alignItems: "center", gap: 5,
          border: "0.5px solid var(--color-border-secondary)",
          borderRadius: 4, padding: "3px 8px",
          background: "var(--color-background-secondary)",
        }}>
          <Search size={11} color="var(--color-text-secondary)" />
          <input
            placeholder="Filter by drug…"
            value={drugFilter}
            onChange={(e) => { setDrugFilter(e.target.value); setPage(1); }}
            style={{
              background: "none", border: "none", outline: "none",
              fontSize: 10, color: "var(--color-text-primary)", width: 120,
            }}
          />
        </div>
      </div>

      {/* Signal feed */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 12px" }}>
        {isLoading ? (
          <div style={{ padding: "40px 0", textAlign: "center", fontSize: 10, color: "var(--color-text-secondary)" }}>
            Loading signals…
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}>
            <AlertTriangle size={24} color="var(--color-text-secondary)" style={{ marginBottom: 8 }} />
            <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>No signals found for this filter.</div>
          </div>
        ) : (
          items.map((sig) => (
            <SignalItem
              key={sig.id}
              signal={sig}
              isAILoading={aiLoadingId === sig.id}
              onTriage={(action) => triage.mutate({ id: sig.id, action })}
              onTriageAI={async () => {
                setAILoadingId(sig.id);
                try { await triageAI.mutateAsync(sig.id); } finally { setAILoadingId(null); }
              }}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          display: "flex", justifyContent: "center", alignItems: "center", gap: 8,
          padding: "8px", borderTop: "0.5px solid var(--color-border-tertiary)",
          fontSize: 10, color: "var(--color-text-secondary)", flexShrink: 0,
        }}>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
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
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
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
      )}
    </div>
  );
}
