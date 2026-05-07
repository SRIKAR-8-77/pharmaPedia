import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createProject, listGlobalSources, discoverSources, addConfirmedSource } from "../api/client";
import { X, Search, Bot, CheckCircle, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";

const SOURCE_DESCS = {
  faers:       "FDA adverse event reports · official API",
  pubmed:      "Peer-reviewed research abstracts · NCBI",
  google_news: "News articles · Google News RSS",
  reddit:      "Patient discussions · RSS + PRAW",
  rss:         "Custom RSS feed",
  api:         "Custom JSON API",
  twitter:     "Twitter/X · twitterapi.io",
};

const SOURCE_STATUS = {
  faers: "green", pubmed: "green", google_news: "green",
  rss: "green", api: "green", reddit: "green", twitter: "amber",
};


const STEPS = ["Name", "Keywords", "Sources", "Date Range", "Alerts", "Launch"];

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

const DISCOVERY_STEPS = [
  "Searching the web for patient communities and clinical data sources…",
  "Probing candidate URLs for RSS feeds and public APIs…",
  "Asking AI to assess relevance and timestamp support…",
  "Ranking results…",
];

function StepSources({ sources, setSources, keywords }) {
  const qc = useQueryClient();
  const { data: globalSources = [], isLoading } = useQuery({
    queryKey: ["global-sources"],
    queryFn: listGlobalSources,
  });

  // Pre-select all sources once loaded
  useEffect(() => {
    if (globalSources.length > 0 && sources.length === 0) {
      setSources(globalSources.map((gs) => gs.id));
    }
  }, [globalSources]);

  const toggle = (id) =>
    setSources((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);

  // Discovery state
  const [discoverKw, setDiscoverKw] = useState("");
  const [showDiscover, setShowDiscover] = useState(false);
  const [discoverResults, setDiscoverResults] = useState(null);
  const [addedDomains, setAddedDomains] = useState(new Set());
  const [progressStep, setProgressStep] = useState(0);
  const progressRef = useRef(null);

  const discoverMut = useMutation({
    mutationFn: discoverSources,
    onSuccess: (data) => {
      clearInterval(progressRef.current);
      setDiscoverResults(data);
    },
    onError: () => clearInterval(progressRef.current),
  });

  const addMut = useMutation({
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
      qc.invalidateQueries({ queryKey: ["global-sources"] });
      // auto-select the new source
      setSources((prev) => prev.includes(saved.id) ? prev : [...prev, saved.id]);
      toast.success(`"${saved.name}" added to registry`);
    },
    onError: (err) => toast.error(err?.response?.data?.detail || "Failed to add source"),
  });

  const startDiscover = () => {
    const kw = discoverKw.trim() || keywords[0] || "";
    if (!kw) return;
    setDiscoverResults(null);
    setProgressStep(0);
    let step = 0;
    progressRef.current = setInterval(() => {
      step = Math.min(step + 1, DISCOVERY_STEPS.length - 1);
      setProgressStep(step);
    }, 5000);
    discoverMut.mutate(kw);
  };

  const available = discoverResults?.available || [];
  const suggestions = discoverResults?.suggestions || [];
  const alreadyTracked = discoverResults?.already_tracked || [];

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Select data sources</div>
      {isLoading && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", padding: "10px 0" }}>Loading sources…</div>
      )}
      {globalSources.map((gs) => {
        const on = sources.includes(gs.id);
        const status = SOURCE_STATUS[gs.source_type] || "green";
        const desc = SOURCE_DESCS[gs.source_type] || gs.source_type;
        return (
          <div
            key={gs.id}
            style={{
              display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
              border: "0.5px solid " + (on ? "var(--color-border-primary)" : "var(--color-border-tertiary)"),
              borderRadius: 5, marginBottom: 5, cursor: "pointer",
              background: on ? "var(--color-background-secondary)" : "var(--color-background-primary)",
              transition: "all 0.12s",
            }}
            onClick={() => toggle(gs.id)}
          >
            <div style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: DOT_COLORS[status] }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-primary)" }}>{gs.name}</div>
              <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>{desc}</div>
            </div>
            <Toggle on={on} onClick={(e) => { e.stopPropagation(); toggle(gs.id); }} />
          </div>
        );
      })}

      {/* Discover panel */}
      <div style={{ marginTop: 10, borderTop: "0.5px solid var(--color-border-tertiary)", paddingTop: 10 }}>
        {!showDiscover ? (
          <button
            onClick={() => { setShowDiscover(true); setDiscoverKw(keywords[0] || ""); }}
            style={{
              fontSize: 10, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
              border: "0.5px solid var(--color-border-secondary)", background: "transparent",
              color: "var(--color-text-secondary)", display: "flex", alignItems: "center", gap: 5,
            }}
          >
            <Bot size={11} /> Find more sources with AI →
          </button>
        ) : (
          <div>
            <div style={{ fontSize: 10, fontWeight: 500, marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
              <span>AI source discovery</span>
              <span
                style={{ fontSize: 9, color: "var(--color-text-secondary)", cursor: "pointer" }}
                onClick={() => { setShowDiscover(false); setDiscoverResults(null); }}
              >
                ✕ close
              </span>
            </div>

            {/* Search bar */}
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <input
                value={discoverKw}
                onChange={(e) => setDiscoverKw(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && startDiscover()}
                placeholder="Keyword to search (e.g. ozempic side effects)"
                style={{
                  flex: 1, padding: "4px 8px",
                  background: "var(--color-background-secondary)",
                  border: "0.5px solid var(--color-border-tertiary)",
                  borderRadius: 4, fontSize: 10,
                  color: "var(--color-text-primary)", outline: "none",
                }}
              />
              <button
                onClick={startDiscover}
                disabled={!discoverKw.trim() || discoverMut.isPending}
                style={{
                  padding: "4px 10px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                  border: "0.5px solid var(--color-border-secondary)",
                  background: "var(--color-background-secondary)",
                  color: "var(--color-text-primary)",
                  opacity: !discoverKw.trim() || discoverMut.isPending ? 0.5 : 1,
                  display: "flex", alignItems: "center", gap: 4,
                }}
              >
                <Search size={10} /> {discoverMut.isPending ? "Searching…" : "Search"}
              </button>
            </div>

            {/* Progress log */}
            {discoverMut.isPending && (
              <div style={{
                padding: "10px 12px", background: "var(--color-background-secondary)",
                borderRadius: 5, marginBottom: 8,
              }}>
                {DISCOVERY_STEPS.map((msg, i) => (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", gap: 7,
                    fontSize: 9, lineHeight: 1.8,
                    color: i <= progressStep ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                    opacity: i <= progressStep ? 1 : 0.4,
                  }}>
                    {i < progressStep ? (
                      <CheckCircle size={9} color="var(--color-green)" />
                    ) : i === progressStep ? (
                      <RefreshCw size={9} style={{ animation: "spin 1.2s linear infinite", color: "var(--color-text-secondary)" }} />
                    ) : (
                      <span style={{ width: 9, display: "inline-block" }}>·</span>
                    )}
                    {msg}
                  </div>
                ))}
              </div>
            )}

            {/* Error */}
            {discoverMut.isError && (
              <div style={{ fontSize: 9, color: "var(--color-red-text)", marginBottom: 8, padding: "6px 10px", background: "var(--color-background-secondary)", borderRadius: 4 }}>
                Discovery failed: {discoverMut.error?.response?.data?.detail || discoverMut.error?.message || "Check backend logs."}
              </div>
            )}

            {/* Results */}
            {discoverResults && (
              <div>
                {available.length > 0 && available.map((src, i) => (
                  <div key={i} style={{
                    padding: "8px 10px", borderRadius: 5, marginBottom: 6,
                    border: `0.5px solid var(--color-green)30`,
                    background: "var(--color-background-secondary)",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 10, fontWeight: 500 }}>{src.name || src.domain}</div>
                        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 2 }}>
                          {src.access_type?.toUpperCase()} · {src.supports_date_range ? "⏱ supports date filter" : "no date filter"}
                        </div>
                        {src.reason && <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 2, lineHeight: 1.4 }}>{src.reason}</div>}
                      </div>
                      {addedDomains.has(src.domain) ? (
                        <span style={{ fontSize: 9, color: "var(--color-green)", display: "flex", alignItems: "center", gap: 3, flexShrink: 0 }}>
                          <CheckCircle size={9} /> Added
                        </span>
                      ) : (
                        <button
                          onClick={() => addMut.mutate(src)}
                          disabled={addMut.isPending}
                          style={{
                            fontSize: 9, padding: "3px 8px", borderRadius: 3, cursor: "pointer", flexShrink: 0,
                            border: "0.5px solid var(--color-green)", background: "var(--color-green-bg)",
                            color: "var(--color-green-text)", opacity: addMut.isPending ? 0.6 : 1,
                          }}
                        >
                          + Add to registry
                        </button>
                      )}
                    </div>
                  </div>
                ))}

                {suggestions.length > 0 && (
                  <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 6 }}>
                    <span style={{ fontWeight: 500 }}>Relevant but no free access: </span>
                    {suggestions.map((s) => s.name || s.domain).join(", ")}
                  </div>
                )}

                {alreadyTracked.length > 0 && (
                  <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 6 }}>
                    <span style={{ fontWeight: 500 }}>Already in registry: </span>
                    {alreadyTracked.map((t) => t.domain).join(", ")}
                  </div>
                )}

                {available.length === 0 && suggestions.length === 0 && (
                  <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
                    No new accessible sources found. Try a more specific keyword.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StepDateRange({ dateFrom, setDateFrom, dateTo, setDateTo, mode, setMode }) {
  const inputStyle = {
    width: "100%", padding: "5px 8px", boxSizing: "border-box",
    background: "var(--color-background-secondary)",
    border: "0.5px solid var(--color-border-tertiary)",
    borderRadius: 4, fontSize: 11, color: "var(--color-text-primary)", outline: "none",
  };
  const today = new Date().toISOString().split("T")[0];

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Data collection window</div>
      <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 14, lineHeight: 1.6 }}>
        Choose how far back to pull historical data and whether to keep monitoring live.
      </div>

      {/* Mode selection */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {[
          { id: "live",       label: "Live",          desc: "Start from now, monitor continuously" },
          { id: "historical", label: "Historical",     desc: "Pull past data, then go live" },
          { id: "fixed",      label: "Fixed range",   desc: "Specific start + end date only" },
        ].map((m) => (
          <div
            key={m.id}
            onClick={() => setMode(m.id)}
            style={{
              flex: 1, padding: "8px 10px", borderRadius: 5, cursor: "pointer",
              border: `0.5px solid ${mode === m.id ? "var(--color-border-primary)" : "var(--color-border-tertiary)"}`,
              background: mode === m.id ? "var(--color-background-secondary)" : "var(--color-background-primary)",
              transition: "all 0.12s",
            }}
          >
            <div style={{ fontSize: 10, fontWeight: 500, color: "var(--color-text-primary)", marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", lineHeight: 1.4 }}>{m.desc}</div>
          </div>
        ))}
      </div>

      {/* Date inputs */}
      {(mode === "historical" || mode === "fixed") && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 12px" }}>
          <div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>
              Start date *
            </div>
            <input
              type="date"
              max={today}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginBottom: 3 }}>
              {mode === "fixed" ? "End date *" : "End date (blank = keep live)"}
            </div>
            <input
              type="date"
              min={dateFrom || undefined}
              max={mode === "fixed" ? today : undefined}
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              style={inputStyle}
            />
          </div>
        </div>
      )}

      {mode === "live" && (
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)", padding: "8px 10px", background: "var(--color-background-secondary)", borderRadius: 4 }}>
          Monitoring starts immediately. Sources will be polled on their scheduled cadence (Reddit: real-time, news: daily, PubMed: weekly, FAERS: daily).
        </div>
      )}

      {mode === "historical" && (
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 8, lineHeight: 1.5 }}>
          A batch scrape will fetch all data from the start date. After it finishes, live monitoring continues automatically.
        </div>
      )}

      {mode === "fixed" && (
        <div style={{ fontSize: 9, color: "var(--color-amber)", marginTop: 8, lineHeight: 1.5 }}>
          Fixed range: only the specified window will be scraped. No live monitoring after the end date.
        </div>
      )}
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
  const { data: globalSources = [] } = useQuery({ queryKey: ["global-sources"], queryFn: listGlobalSources });
  const selectedNames = globalSources.filter((gs) => sources.includes(gs.id)).map((gs) => gs.name);
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>Ready to launch</div>
      <div style={{ background: "var(--color-background-secondary)", borderRadius: 6, padding: "10px 12px", fontSize: 10, lineHeight: 1.8 }}>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Project:</span> {name || "—"}</div>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Keywords:</span> {keywords.join(", ") || "—"}</div>
        <div><span style={{ color: "var(--color-text-secondary)" }}>Sources:</span> {selectedNames.join(", ") || "—"}</div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function ProjectCreate() {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState([]);
  const [sources, setSources] = useState([]);  // UUIDs from global_sources, populated by StepSources
  const [mode, setMode] = useState("live");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
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
      selected_source_ids: sources,
      alert_rules: {},
      date_from: dateFrom ? new Date(dateFrom).toISOString() : null,
      date_to: (dateTo && mode === "fixed") ? new Date(dateTo).toISOString() : null,
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
            {step === 2 && <StepSources sources={sources} setSources={setSources} keywords={keywords} />}
            {step === 3 && <StepDateRange dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} mode={mode} setMode={setMode} />}
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
