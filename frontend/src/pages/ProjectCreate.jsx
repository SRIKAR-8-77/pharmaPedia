import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject } from "../api/client";
import { X } from "lucide-react";
import toast from "react-hot-toast";

const SOURCES = [
  { id: "reddit",  label: "Reddit",         desc: "PRAW + RSS · subreddit stream",   status: "green" },
  { id: "twitter", label: "Twitter / X",     desc: "twitterapi.io · keyword search",  status: "green" },
  { id: "rss",     label: "HealthUnlocked",  desc: "Scrapy spider · auto-config",      status: "amber" },
  { id: "forum",   label: "Drugs.com",       desc: "RSS feed · review comments",       status: "amber" },
];

const LATENCIES = [
  { id: "realtime", label: "Real-time", desc: "Every 60s" },
  { id: "daily",    label: "Daily",     desc: "Once per day" },
  { id: "weekly",   label: "Weekly",    desc: "Once per week" },
];

const STEPS = ["Name", "Keywords", "Sources", "Latency", "Alerts", "Launch"];

const DOT_COLORS = { green: "var(--color-green)", amber: "var(--color-amber)", red: "var(--color-red)" };

function Toggle({ on, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        width: 28, height: 14, borderRadius: 7,
        background: on ? "var(--color-green)" : "var(--color-border-secondary)",
        position: "relative", flexShrink: 0, cursor: "pointer",
        transition: "background 0.12s",
      }}
    >
      <div style={{
        position: "absolute", width: 10, height: 10,
        background: "#fff", borderRadius: "50%", top: 2,
        left: on ? 16 : 2, transition: "left 0.12s",
      }} />
    </div>
  );
}

// ── Steps ─────────────────────────────────────────────────────────────────────

function StepIndicator({ current }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 20 }}>
      {STEPS.map((label, i) => (
        <div key={label} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : 0 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
            <div style={{
              width: 22, height: 22, borderRadius: "50%",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: 500,
              background: i < current
                ? "var(--color-green)" : i === current
                ? "var(--color-background-secondary)" : "transparent",
              border: i < current
                ? "1.5px solid var(--color-green)" : i === current
                ? "1.5px solid var(--color-border-primary)"
                : "1.5px solid var(--color-border-secondary)",
              color: i < current
                ? "#fff" : i === current
                ? "var(--color-text-primary)"
                : "var(--color-text-secondary)",
            }}>
              {i < current ? "✓" : i + 1}
            </div>
            <span style={{
              fontSize: 9,
              color: i === current ? "var(--color-text-primary)" : "var(--color-text-secondary)",
            }}>{label}</span>
          </div>
          {i < STEPS.length - 1 && (
            <div style={{
              flex: 1, height: 1,
              background: "var(--color-border-tertiary)",
              margin: "0 4px", marginTop: -10,
            }} />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Step panels ───────────────────────────────────────────────────────────────

function StepName({ name, setName }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12, color: "var(--color-text-primary)" }}>
        Name your project
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 4 }}>Project name</div>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Ozempic Safety Monitor"
          style={{
            width: "100%", padding: "5px 8px",
            background: "var(--color-background-secondary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: 4, fontSize: 11,
            color: "var(--color-text-primary)", outline: "none",
          }}
        />
      </div>
    </div>
  );
}

function StepKeywords({ keywords, setKeywords }) {
  const [kw, setKw] = useState("");

  const add = () => {
    const parts = kw.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    const fresh = parts.filter((p) => !keywords.includes(p));
    if (fresh.length) setKeywords([...keywords, ...fresh]);
    setKw("");
  };

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Keywords to monitor</div>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <input
          value={kw}
          onChange={(e) => setKw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder="Type keyword, press Enter"
          style={{
            flex: 1, padding: "5px 8px",
            background: "var(--color-background-secondary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: 4, fontSize: 11,
            color: "var(--color-text-primary)", outline: "none",
          }}
        />
        <button
          onClick={add}
          style={{
            padding: "5px 10px", borderRadius: 4, fontSize: 11,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)",
          }}
        >
          Add
        </button>
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {keywords.map((k) => (
          <span key={k} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "2px 7px", borderRadius: 3,
            background: "var(--color-background-secondary)",
            border: "0.5px solid var(--color-border-secondary)",
            color: "var(--color-text-primary)", fontSize: 10,
          }}>
            {k}
            <X size={10} style={{ cursor: "pointer", color: "var(--color-text-secondary)" }}
              onClick={() => setKeywords(keywords.filter((x) => x !== k))} />
          </span>
        ))}
      </div>
    </div>
  );
}

function StepSources({ sources, setSources }) {
  const toggle = (id) =>
    setSources((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Select data sources</div>
      {SOURCES.map((s) => {
        const on = sources.includes(s.id);
        return (
          <div
            key={s.id}
            style={{
              display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
              border: "0.5px solid " + (on ? "var(--color-border-primary)" : "var(--color-border-tertiary)"),
              borderRadius: 5, marginBottom: 5, cursor: "pointer",
              background: on ? "var(--color-background-secondary)" : "var(--color-background-primary)",
              transition: "all 0.12s",
            }}
            onClick={() => toggle(s.id)}
          >
            <div style={{
              width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
              background: DOT_COLORS[s.status],
            }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-primary)" }}>{s.label}</div>
              <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>{s.desc}</div>
            </div>
            <Toggle on={on} onClick={(e) => { e.stopPropagation(); toggle(s.id); }} />
          </div>
        );
      })}
      <div style={{ marginTop: 8, fontSize: 10, color: "var(--color-text-secondary)" }}>
        Don't see your source?{" "}
        <span style={{ color: "var(--color-purple)", cursor: "pointer" }}>
          Discover new sources via AI agent →
        </span>
      </div>
    </div>
  );
}

function StepLatency({ sources, latency, setLatency }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Set polling frequency</div>
      {sources.length === 0 && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>No sources selected.</div>
      )}
      {sources.map((src) => (
        <div key={src} style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, fontWeight: 500, marginBottom: 6, textTransform: "capitalize" }}>{src}</div>
          <div style={{ display: "flex", gap: 6 }}>
            {LATENCIES.map((l) => {
              const active = (latency[src] || "daily") === l.id;
              return (
                <button
                  key={l.id}
                  onClick={() => setLatency((prev) => ({ ...prev, [src]: l.id }))}
                  style={{
                    flex: 1, padding: "6px 8px", borderRadius: 5,
                    border: "0.5px solid " + (active ? "var(--color-border-primary)" : "var(--color-border-tertiary)"),
                    background: active ? "var(--color-background-secondary)" : "var(--color-background-primary)",
                    color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                    fontSize: 10, cursor: "pointer",
                  }}
                >
                  <div style={{ fontWeight: 500 }}>{l.label}</div>
                  <div style={{ fontSize: 9, opacity: 0.8 }}>{l.desc}</div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function StepAlerts() {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Alert configuration</div>
      <div style={{ fontSize: 10, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
        High-severity signals (confidence ≥ 0.85) will be flagged immediately.<br />
        Medium signals are batched into daily digests.<br />
        You can customise thresholds after project creation.
      </div>
    </div>
  );
}

function StepLaunch({ name, keywords, sources }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Ready to launch</div>
      <div style={{ background: "var(--color-background-secondary)", borderRadius: 6, padding: "10px 12px", fontSize: 10, lineHeight: 1.8 }}>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Project:</span> {name || "—"}</div>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Keywords:</span> {keywords.join(", ") || "—"}</div>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Sources:</span> {sources.join(", ") || "—"}</div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function ProjectCreate() {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState([]);
  const [sources, setSources] = useState(["reddit", "twitter"]);
  const [latency, setLatency] = useState({});
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { mutate, isPending } = useMutation({
    mutationFn: createProject,
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(`Project "${project.name}" created!`);
      navigate(`/projects/${project.id}/dashboard`);
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || "Failed to create project");
    },
  });

  const canNext =
    step === 0 ? name.trim().length > 0 :
    step === 1 ? keywords.length > 0 :
    step === 2 ? sources.length > 0 : true;

  const handleFinish = () => {
    mutate({
      name: name.trim(),
      keywords,
      sources,
      alert_rules: Object.fromEntries(
        sources.map((s) => [s, { latency: latency[s] || "daily" }])
      ),
    });
  };

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 500 }}>New project</span>
        <button
          onClick={() => navigate("/projects")}
          style={{
            marginLeft: "auto", fontSize: 10, padding: "3px 8px", borderRadius: 4,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-secondary)", cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>

      {/* Wizard body */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px" }}>
        <div style={{ maxWidth: 480, margin: "0 auto" }}>
          <StepIndicator current={step} />

          {/* Step card */}
          <div style={{
            background: "var(--color-background-primary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: "var(--border-radius-lg)",
            padding: 16, marginBottom: 14,
          }}>
            {step === 0 && <StepName name={name} setName={setName} />}
            {step === 1 && <StepKeywords keywords={keywords} setKeywords={setKeywords} />}
            {step === 2 && <StepSources sources={sources} setSources={setSources} />}
            {step === 3 && <StepLatency sources={sources} latency={latency} setLatency={setLatency} />}
            {step === 4 && <StepAlerts />}
            {step === 5 && <StepLaunch name={name} keywords={keywords} sources={sources} />}
          </div>

          {/* Footer nav */}
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <button
              onClick={() => setStep((s) => s - 1)}
              disabled={step === 0}
              style={{
                fontSize: 11, padding: "5px 14px", borderRadius: 5, cursor: "pointer",
                border: "0.5px solid var(--color-border-secondary)",
                background: "var(--color-background-primary)",
                color: step === 0 ? "var(--color-text-secondary)" : "var(--color-text-primary)",
              }}
            >
              ← Back
            </button>

            {step < STEPS.length - 1 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                disabled={!canNext}
                style={{
                  fontSize: 11, padding: "5px 14px", borderRadius: 5, cursor: canNext ? "pointer" : "not-allowed",
                  border: "0.5px solid var(--color-border-secondary)",
                  background: "var(--color-background-secondary)",
                  color: canNext ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                  fontWeight: 500,
                }}
              >
                Next →
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={isPending}
                style={{
                  fontSize: 11, padding: "5px 14px", borderRadius: 5,
                  border: "0.5px solid var(--color-green)",
                  background: "var(--color-green-bg)",
                  color: "var(--color-green-text)", fontWeight: 500,
                  cursor: isPending ? "not-allowed" : "pointer",
                }}
              >
                {isPending ? "Creating…" : "Launch project"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
