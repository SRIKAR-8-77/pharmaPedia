import { useState, useEffect, useRef, useMemo } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { listSignals, copilotChat, getCanvas, updateCanvas } from "../api/client";
import { Pin, X, Network, Send, PlusSquare, CheckSquare } from "lucide-react";

// ─── Shared style constants ───────────────────────────────────────────────────

const SEV_S = {
  HIGH: { bg: "var(--color-red-bg)",   color: "var(--color-red-text)",   label: "HIGH" },
  MED:  { bg: "var(--color-amber-bg)", color: "var(--color-amber-text)", label: "MED"  },
  LOW:  { bg: "var(--color-green-bg)", color: "var(--color-green-text)", label: "LOW"  },
};

const TYPE_STYLE = {
  drug:    { bg: "#e6f1fb", color: "#185fa5", stroke: "#378add" },
  symptom: { bg: "#faeeda", color: "#854f0b", stroke: "#ef9f27" },
};

// ─── Pure graph builder ───────────────────────────────────────────────────────

function buildGraph(signals) {
  if (!signals?.items?.length) return { nodes: [], edges: [] };
  const drugMap = {}, symptomMap = {}, edgeMap = {};
  for (const sig of signals.items) {
    const d = sig.drug, s = sig.symptom;
    if (d) drugMap[d] = (drugMap[d] || 0) + 1;
    if (s) symptomMap[s] = (symptomMap[s] || 0) + 1;
    if (d && s) {
      const key = `${d}||${s}`;
      edgeMap[key] = edgeMap[key] || { drug: d, symptom: s, count: 0, maxSev: "LOW" };
      edgeMap[key].count += 1;
      if (sig.severity === "HIGH") edgeMap[key].maxSev = "HIGH";
      else if (sig.severity === "MED" && edgeMap[key].maxSev !== "HIGH") edgeMap[key].maxSev = "MED";
    }
  }
  const topDrugs    = Object.entries(drugMap).sort((a, b) => b[1] - a[1]).slice(0, 7);
  const topSymptoms = Object.entries(symptomMap).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const cx = 380, cy = 240, r1 = 120, r2 = 200;
  const nodes = [];
  topDrugs.forEach(([name, count], i) => {
    const a = (2 * Math.PI * i) / topDrugs.length - Math.PI / 2;
    nodes.push({ id: `d:${name}`, label: name, type: "drug", count,
      x: cx + r1 * Math.cos(a), y: cy + r1 * Math.sin(a) });
  });
  topSymptoms.forEach(([name, count], i) => {
    const a = (2 * Math.PI * i) / topSymptoms.length - Math.PI / 2;
    nodes.push({ id: `s:${name}`, label: name, type: "symptom", count,
      x: cx + r2 * Math.cos(a), y: cy + r2 * Math.sin(a) });
  });
  const nodeIds = new Set(nodes.map((n) => n.id));
  const edges = Object.values(edgeMap)
    .filter((e) => nodeIds.has(`d:${e.drug}`) && nodeIds.has(`s:${e.symptom}`))
    .map((e) => ({ from: `d:${e.drug}`, to: `s:${e.symptom}`, count: e.count, maxSev: e.maxSev }));
  return { nodes, edges };
}

// ─── Knowledge Graph (SVG) ────────────────────────────────────────────────────

const SEV_EDGE = { HIGH: "#e24b4a60", MED: "#ef9f2750", LOW: "#378add30" };

function KnowledgeGraph({ signals, isLoading, selectedNodeId, cardIds, onNodeClick }) {
  const graph = useMemo(() => buildGraph(signals), [signals]);
  const [hover, setHover] = useState(null);

  if (isLoading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
        height: "100%", color: "var(--color-text-secondary)", fontSize: 10 }}>
        Loading signal graph…
      </div>
    );
  }
  if (!graph.nodes.length) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
        height: "100%", flexDirection: "column", gap: 8, color: "var(--color-text-secondary)" }}>
        <Network size={28} />
        <span style={{ fontSize: 10 }}>No signal data yet. Run the pipeline to populate.</span>
      </div>
    );
  }

  return (
    <svg width="100%" height="100%" viewBox="0 0 760 480" style={{ overflow: "visible" }}>
      {graph.edges.map((e, i) => {
        const from = graph.nodes.find((n) => n.id === e.from);
        const to   = graph.nodes.find((n) => n.id === e.to);
        if (!from || !to) return null;
        const hl = hover && (hover === e.from || hover === e.to);
        return (
          <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke={hl ? SEV_EDGE.HIGH : SEV_EDGE[e.maxSev]}
            strokeWidth={Math.max(1, Math.min(e.count, 4))}
          />
        );
      })}
      {graph.nodes.map((node) => {
        const ts = TYPE_STYLE[node.type];
        const r = Math.max(16, Math.min(node.count * 4 + 12, 32));
        const isHover    = hover === node.id;
        const isSelected = selectedNodeId === node.id;
        const hasCard    = cardIds.has(node.id);
        const strokeColor = isSelected ? "#7c3aed" : hasCard ? "#059669" : ts.stroke;
        const strokeW     = isSelected || hasCard ? 2.5 : isHover ? 2 : 1;
        return (
          <g key={node.id} style={{ cursor: "pointer" }}
            onMouseEnter={() => setHover(node.id)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onNodeClick(node)}
          >
            {/* Selection ring */}
            {isSelected && (
              <circle cx={node.x} cy={node.y} r={r + 7}
                fill="none" stroke="#7c3aed" strokeWidth={1.5} strokeDasharray="3 2" opacity={0.6} />
            )}
            <circle cx={node.x} cy={node.y} r={r + (isHover ? 3 : 0)}
              fill={isSelected ? "#f5f0ff" : ts.bg}
              stroke={strokeColor} strokeWidth={strokeW}
              style={{ transition: "r 0.12s" }}
            />
            <text x={node.x} y={node.y} textAnchor="middle" dominantBaseline="middle"
              fontSize={9} fill={ts.color} fontWeight={600}
              style={{ pointerEvents: "none", userSelect: "none" }}
            >
              {node.label.length > 10 ? node.label.slice(0, 9) + "…" : node.label}
            </text>
            {/* Card-added indicator (green dot) */}
            {hasCard && (
              <circle cx={node.x + r - 2} cy={node.y - r + 2} r={5}
                fill="#059669" stroke="white" strokeWidth={1} />
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ─── Node detail sidebar ──────────────────────────────────────────────────────

function SeverityBadge({ severity }) {
  const s = SEV_S[severity] || SEV_S.LOW;
  return (
    <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2, fontWeight: 600,
      background: s.bg, color: s.color, flexShrink: 0 }}>
      {s.label}
    </span>
  );
}

function SignalRow({ sig }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
      {/* Top row: severity + drug/symptom tags + triage */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
        <SeverityBadge severity={sig.severity} />
        {sig.drug && (
          <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2,
            background: "#e6f1fb", color: "#185fa5" }}>
            {sig.drug}
          </span>
        )}
        {sig.symptom && sig.symptom !== sig.drug && (
          <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2,
            background: "#faeeda", color: "#854f0b" }}>
            {sig.symptom}
          </span>
        )}
        {sig.triage_action && sig.triage_action !== "pending" && (
          <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 2,
            background: "var(--color-background-secondary)", color: "var(--color-text-secondary)",
            border: "0.5px solid var(--color-border-secondary)" }}>
            {sig.triage_action}
          </span>
        )}
      </div>

      {/* Context window */}
      {sig.context_window && (
        <div style={{ fontSize: 9, lineHeight: 1.5, color: "var(--color-text-primary)",
          marginBottom: 3, fontStyle: "italic" }}>
          "{sig.context_window}"
        </div>
      )}

      {/* Meta */}
      <div style={{ fontSize: 9, color: "var(--color-text-secondary)", display: "flex", gap: 6 }}>
        {sig.causality && <span>{sig.causality}</span>}
        <span>conf {((sig.confidence || 0) * 100).toFixed(0)}%</span>
        {sig.meddra_term && <span style={{ color: "var(--color-green-text)" }}>{sig.meddra_term}</span>}
      </div>
    </div>
  );
}

function NodeDetailSidebar({ node, relatedSignals, isCardAdded, onAddCard, onClose }) {
  const ts = TYPE_STYLE[node.type] || TYPE_STYLE.drug;
  const highCount = relatedSignals.filter((s) => s.severity === "HIGH").length;
  const medCount  = relatedSignals.filter((s) => s.severity === "MED").length;

  return (
    <div style={{
      width: 280, borderLeft: "0.5px solid var(--color-border-tertiary)",
      display: "flex", flexDirection: "column", flexShrink: 0,
      background: "var(--color-background-primary)",
    }}>
      {/* Header */}
      <div style={{ padding: "10px 12px", borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 8, fontWeight: 700, padding: "1px 5px", borderRadius: 2,
              background: ts.bg, color: ts.color, textTransform: "uppercase", display: "inline-block", marginBottom: 4 }}>
              {node.type}
            </span>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {node.label}
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer",
            padding: 3, color: "var(--color-text-secondary)", flexShrink: 0 }}>
            <X size={13} />
          </button>
        </div>

        {/* Signal count summary */}
        <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
          <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
            {relatedSignals.length} signal{relatedSignals.length !== 1 ? "s" : ""}
          </span>
          {highCount > 0 && (
            <span style={{ fontSize: 9, color: "var(--color-red-text)", fontWeight: 500 }}>
              {highCount} HIGH
            </span>
          )}
          {medCount > 0 && (
            <span style={{ fontSize: 9, color: "var(--color-amber-text)", fontWeight: 500 }}>
              {medCount} MED
            </span>
          )}
        </div>

        {/* Add card button */}
        <button
          onClick={onAddCard}
          disabled={isCardAdded}
          style={{
            width: "100%", padding: "5px 0", borderRadius: 4, fontSize: 10,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
            border: `0.5px solid ${isCardAdded ? "var(--color-green)" : "var(--color-border-secondary)"}`,
            background: isCardAdded ? "var(--color-green-bg)" : "var(--color-background-secondary)",
            color: isCardAdded ? "var(--color-green-text)" : "var(--color-text-primary)",
            cursor: isCardAdded ? "default" : "pointer",
            fontWeight: 500,
          }}
        >
          {isCardAdded
            ? <><CheckSquare size={11} /> Added to canvas</>
            : <><PlusSquare size={11} /> Add as insight card</>}
        </button>
      </div>

      {/* Signal list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 12px" }}>
        {relatedSignals.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center",
            fontSize: 10, color: "var(--color-text-secondary)" }}>
            No signals linked to this {node.type}.
          </div>
        ) : (
          relatedSignals.map((sig) => <SignalRow key={sig.id} sig={sig} />)
        )}
      </div>
    </div>
  );
}

// ─── Draggable insight card ───────────────────────────────────────────────────

function CanvasCard({ card, onPin, onClose, onMove }) {
  // Handlers created inside onMouseDown — no listener leak across renders
  function onMouseDown(e) {
    if (e.target.closest("button")) return;
    e.preventDefault();
    const startX = e.clientX, startY = e.clientY;
    const startCardX = card.x, startCardY = card.y;
    function handleMove(ev) {
      onMove(card.id, startCardX + ev.clientX - startX, startCardY + ev.clientY - startY);
    }
    function handleUp() {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  }

  const ts = TYPE_STYLE[card.type] || TYPE_STYLE.drug;

  return (
    <div onMouseDown={onMouseDown} style={{
      position: "absolute", left: card.x, top: card.y, width: 192,
      background: "var(--color-background-primary)",
      border: "0.5px solid " + (card.pinned ? "#7c3aed" : "var(--color-border-secondary)"),
      borderRadius: 6, padding: "8px", cursor: "grab",
      zIndex: card.pinned ? 10 : 5, userSelect: "none",
      boxShadow: card.pinned ? "0 0 0 2px #7c3aed22, 0 2px 8px rgba(0,0,0,0.08)" : "0 2px 8px rgba(0,0,0,0.07)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ fontSize: 8, fontWeight: 700, padding: "1px 4px", borderRadius: 2,
          background: ts.bg, color: ts.color, textTransform: "uppercase" }}>
          {card.type}
        </span>
        <div style={{ display: "flex", gap: 3 }}>
          <button onClick={() => onPin(card.id)} title={card.pinned ? "Unpin" : "Pin"}
            style={{ background: "none", border: "none", cursor: "pointer", padding: 1 }}>
            <Pin size={10} color={card.pinned ? "#7c3aed" : "var(--color-text-secondary)"} />
          </button>
          <button onClick={() => onClose(card.id)} title="Remove"
            style={{ background: "none", border: "none", cursor: "pointer", padding: 1 }}>
            <X size={10} color="var(--color-text-secondary)" />
          </button>
        </div>
      </div>

      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 5 }}>
        {card.label}
      </div>

      {/* Top 3 signals preview */}
      {card.signals?.slice(0, 3).map((s, i) => {
        const ss = SEV_S[s.severity] || SEV_S.LOW;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3, fontSize: 9 }}>
            <span style={{ padding: "1px 3px", borderRadius: 2, background: ss.bg, color: ss.color,
              fontWeight: 600, flexShrink: 0 }}>
              {s.severity}
            </span>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              color: "var(--color-text-secondary)" }}>
              {s.symptom || s.drug || s.context_window?.slice(0, 35)}
            </span>
          </div>
        );
      })}
      {(card.count || 0) > 3 && (
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginTop: 2 }}>
          +{card.count - 3} more signals
        </div>
      )}
    </div>
  );
}

// ─── AI Copilot panel ─────────────────────────────────────────────────────────

const SUGGESTIONS = ["Summarize HIGH signals", "Top adverse events?", "Ozempic sentiment?", "Search nausea posts"];

function CopilotPanel({ projectId }) {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! Ask me about safety signals, drug trends, or patient sentiment." },
  ]);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState([]);
  const endRef = useRef(null);

  const chat = useMutation({
    mutationFn: (msg) => copilotChat(projectId, { message: msg, conversation_history: history }),
    onSuccess: (data, msg) => {
      setHistory((h) => [...h,
        { role: "user", content: msg },
        { role: "assistant", content: data.text_response },
      ]);
      setMessages((m) => [...m, { role: "assistant", content: data.text_response }]);
    },
    onError: () => {
      setMessages((m) => [...m, { role: "assistant", content: "Request failed. Check your Gemini API key in the backend .env." }]);
    },
  });

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  function send(text) {
    const msg = (text ?? input).trim();
    if (!msg || chat.isPending) return;
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setInput("");
    chat.mutate(msg);
  }

  return (
    <div style={{
      width: 240, borderLeft: "0.5px solid var(--color-border-tertiary)",
      display: "flex", flexDirection: "column",
      background: "var(--color-background-secondary)", flexShrink: 0,
    }}>
      <div style={{ padding: "8px 10px", borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 500, color: "var(--color-text-primary)" }}>AI Copilot</div>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>Powered by Gemini Flash</div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column",
            alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{
              maxWidth: "92%", padding: "5px 8px",
              borderRadius: m.role === "user" ? "8px 8px 2px 8px" : "8px 8px 8px 2px",
              background: m.role === "user" ? "var(--color-blue-bg)" : "var(--color-background-primary)",
              color: m.role === "user" ? "var(--color-blue-text)" : "var(--color-text-primary)",
              fontSize: 10, lineHeight: 1.5,
              border: "0.5px solid " + (m.role === "user" ? "var(--color-blue)" : "var(--color-border-tertiary)"),
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {m.content}
            </div>
          </div>
        ))}
        {chat.isPending && (
          <div style={{ fontSize: 9, color: "var(--color-text-secondary)", fontStyle: "italic", paddingLeft: 2 }}>
            Analyzing…
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Suggestion chips — clicking sends immediately */}
      {messages.length <= 2 && !chat.isPending && (
        <div style={{ padding: "0 10px 6px", display: "flex", flexWrap: "wrap", gap: 4 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 10,
              background: "var(--color-background-primary)",
              border: "0.5px solid var(--color-border-secondary)",
              color: "var(--color-text-secondary)", cursor: "pointer",
            }}>{s}</button>
          ))}
        </div>
      )}

      <div style={{ padding: "6px 8px", borderTop: "0.5px solid var(--color-border-tertiary)",
        display: "flex", gap: 5, flexShrink: 0 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask anything about your data…"
          style={{
            flex: 1, background: "var(--color-background-primary)",
            border: "0.5px solid var(--color-border-tertiary)",
            borderRadius: 4, padding: "4px 7px", fontSize: 10,
            color: "var(--color-text-primary)", outline: "none",
          }}
        />
        <button onClick={() => send()} disabled={!input.trim() || chat.isPending}
          style={{
            padding: "4px 8px", borderRadius: 4,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-primary)",
            cursor: "pointer", display: "flex", alignItems: "center",
            opacity: !input.trim() || chat.isPending ? 0.4 : 1,
          }}>
          <Send size={11} color="var(--color-text-primary)" />
        </button>
      </div>
    </div>
  );
}

// ─── Main Canvas page ─────────────────────────────────────────────────────────

export default function Canvas() {
  const { projectId } = useParams();
  const [tab, setTab]               = useState("graph");
  const [cards, setCards]           = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);   // node clicked in graph
  const saveTimer = useRef(null);
  const loaded    = useRef(false);

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: signals, isLoading: signalsLoading } = useQuery({
    queryKey: ["signals-all", projectId],
    queryFn:  () => listSignals(projectId, { page_size: 100 }),
  });

  const { data: canvasData } = useQuery({
    queryKey: ["canvas", projectId],
    queryFn:  () => getCanvas(projectId),
  });

  // ── Load persisted cards once (merge — never overwrite user additions) ────
  useEffect(() => {
    if (loaded.current || !canvasData) return;
    loaded.current = true;
    if (canvasData.cards?.length) {
      setCards((current) => current.length === 0 ? canvasData.cards : current);
    }
  }, [canvasData]);

  // ── Debounced save whenever cards change (skip until first load resolves) ─
  useEffect(() => {
    if (!projectId || !loaded.current) return;
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      updateCanvas(projectId, cards).catch(() => {});
    }, 800);
    return () => clearTimeout(saveTimer.current);
  }, [cards, projectId]);

  // ── Derived: O(1) lookup for which nodes already have a card ─────────────
  const cardIds = useMemo(() => new Set(cards.map((c) => c.id)), [cards]);

  // ── Related signals for the selected node ─────────────────────────────────
  const relatedSignals = useMemo(() => {
    if (!selectedNode || !signals?.items) return [];
    return signals.items.filter((s) =>
      selectedNode.type === "drug"
        ? s.drug === selectedNode.label
        : s.symptom === selectedNode.label
    );
  }, [selectedNode, signals]);

  // ── Node click: open sidebar (toggle off if same node clicked again) ──────
  function handleNodeClick(node) {
    setSelectedNode((prev) => prev?.id === node.id ? null : node);
  }

  // ── Add insight card from sidebar ─────────────────────────────────────────
  function handleAddCard(node) {
    if (cardIds.has(node.id)) return;
    const nodeSigs = (signals?.items || []).filter((s) =>
      node.type === "drug" ? s.drug === node.label : s.symptom === node.label
    );
    setCards((prev) => [
      ...prev,
      {
        id: node.id, type: node.type, label: node.label,
        x: 40 + (prev.length % 4) * 205,
        y: 40 + Math.floor(prev.length / 4) * 190,
        pinned: false, signals: nodeSigs, count: nodeSigs.length,
      },
    ]);
  }

  const showSidebar = tab === "graph" && selectedNode !== null;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>

      {/* ── Left: graph / canvas area ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Toolbar */}
        <div style={{
          padding: "8px 12px", borderBottom: "0.5px solid var(--color-border-tertiary)",
          display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
          background: "var(--color-background-primary)",
        }}>
          <span style={{ fontSize: 12, fontWeight: 500, flex: 1, color: "var(--color-text-primary)" }}>
            AI Canvas
          </span>

          {/* Tab toggle */}
          <div style={{ display: "flex", gap: 2,
            background: "var(--color-background-secondary)",
            border: "0.5px solid var(--color-border-tertiary)", borderRadius: 5, padding: 3 }}>
            {[
              { key: "graph",  label: "Knowledge graph" },
              { key: "canvas", label: `Insight cards${cards.length ? ` (${cards.length})` : ""}` },
            ].map(({ key, label }) => (
              <button key={key} onClick={() => { setTab(key); if (key === "canvas") setSelectedNode(null); }}
                style={{
                  padding: "3px 10px", borderRadius: 4, border: "none", fontSize: 10, cursor: "pointer",
                  background: tab === key ? "var(--color-background-primary)" : "transparent",
                  color: tab === key ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                  fontWeight: tab === key ? 500 : 400,
                }}>
                {label}
              </button>
            ))}
          </div>

          <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
            {signalsLoading
              ? "Loading…"
              : signals?.items?.length
                ? `${signals.items.length} signals · click a node to inspect`
                : "No signals yet"}
          </span>
        </div>

        {/* Body */}
        <div style={{ flex: 1, position: "relative", overflow: "hidden",
          background: "var(--color-background-secondary)" }}>

          {/* Dot grid */}
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
            opacity: 0.3, pointerEvents: "none" }}>
            <defs>
              <pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
                <circle cx="10" cy="10" r="0.8" fill="var(--color-border-secondary)" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#dots)" />
          </svg>

          {/* ── Graph tab ── */}
          {tab === "graph" && (
            <div style={{ position: "absolute", inset: 0 }}>
              <KnowledgeGraph
                signals={signals}
                isLoading={signalsLoading}
                selectedNodeId={selectedNode?.id ?? null}
                cardIds={cardIds}
                onNodeClick={handleNodeClick}
              />
              {/* Legend */}
              <div style={{ position: "absolute", bottom: 12, left: 12,
                display: "flex", gap: 10, fontSize: 9, color: "var(--color-text-secondary)" }}>
                {[
                  { color: "#378add", label: "Drug" },
                  { color: "#ef9f27", label: "Symptom" },
                  { color: "#7c3aed", label: "Selected" },
                  { color: "#059669", label: "Card added" },
                ].map(({ color, label }) => (
                  <span key={label} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%",
                      background: color, display: "inline-block" }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── Canvas tab ── */}
          {tab === "canvas" && cards.length === 0 && (
            <div style={{ position: "absolute", top: "50%", left: "50%",
              transform: "translate(-50%,-50%)", textAlign: "center",
              color: "var(--color-text-secondary)" }}>
              <div style={{ fontSize: 22, marginBottom: 8 }}>⊞</div>
              <div style={{ fontSize: 10 }}>
                Switch to Knowledge Graph, click a node, then press "Add as insight card".
              </div>
            </div>
          )}

          {/* Draggable cards (all on canvas tab, only pinned on graph tab) */}
          {(tab === "canvas" ? cards : cards.filter((c) => c.pinned)).map((card) => (
            <CanvasCard key={card.id} card={card}
              onPin={(id) => setCards((c) => c.map((x) => x.id === id ? { ...x, pinned: !x.pinned } : x))}
              onClose={(id) => setCards((c) => c.filter((x) => x.id !== id))}
              onMove={(id, x, y) => setCards((c) => c.map((x2) => x2.id === id ? { ...x2, x, y } : x2))}
            />
          ))}
        </div>
      </div>

      {/* ── Middle: node detail sidebar (only on graph tab when node selected) ── */}
      {showSidebar && (
        <NodeDetailSidebar
          node={selectedNode}
          relatedSignals={relatedSignals}
          isCardAdded={cardIds.has(selectedNode.id)}
          onAddCard={() => handleAddCard(selectedNode)}
          onClose={() => setSelectedNode(null)}
        />
      )}

      {/* ── Right: AI Copilot ── */}
      <CopilotPanel projectId={projectId} />
    </div>
  );
}
