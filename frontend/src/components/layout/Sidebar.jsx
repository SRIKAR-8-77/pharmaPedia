import { NavLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listProjects } from "../../api/client";

const NAV = [
  { to: "dashboard", label: "Dashboard",    dot: "green" },
  { to: "signals",   label: "Signals",      dot: "red"   },
  { to: "canvas",    label: "AI Canvas",    dot: "green" },
  { to: "posts",     label: "Post Feed",    dot: null    },
  { to: "reports",   label: "PV Reports",   dot: null    },
];

const DOT_COLORS = {
  green: "var(--color-green)",
  amber: "var(--color-amber)",
  red:   "var(--color-red)",
  null:  "var(--color-border-secondary)",
};

function Dot({ color, size = 6 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", flexShrink: 0,
      background: DOT_COLORS[color] ?? "var(--color-border-secondary)",
    }} />
  );
}

export default function Sidebar() {
  const { projectId } = useParams();
  const { data: projects = [] } = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const active = projects.find((p) => p.id === projectId);

  return (
    <aside style={{
      width: "var(--sidebar-width)",
      minWidth: "var(--sidebar-width)",
      background: "var(--color-background-secondary)",
      borderRight: "0.5px solid var(--color-border-tertiary)",
      display: "flex",
      flexDirection: "column",
      height: "100vh",
      position: "fixed",
      top: 0, left: 0,
      zIndex: 50,
      overflowY: "auto",
    }}>
      {/* Logo */}
      <div style={{
        padding: "10px 10px 10px",
        borderBottom: "0.5px solid var(--color-border-tertiary)",
        marginBottom: 8,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--color-text-primary)", lineHeight: 1.2 }}>
          PharmaSignal
        </div>
        <div style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>
          {active?.name || "Social Intelligence"}
        </div>
      </div>

      {/* Workspace nav — shown when inside a project */}
      {projectId && (
        <div style={{ padding: "0 6px", marginBottom: 4 }}>
          <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-secondary)", padding: "0 6px", marginBottom: 3 }}>
            Workspace
          </div>
          {NAV.map(({ to, label, dot }) => (
            <NavLink
              key={to}
              to={`/projects/${projectId}/${to}`}
              style={({ isActive }) => ({
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 6px", borderRadius: 5,
                fontSize: 11, marginBottom: 1,
                background: isActive ? "var(--color-background-primary)" : "transparent",
                color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                fontWeight: isActive ? 500 : 400,
                textDecoration: "none",
              })}
            >
              <Dot color={dot} />
              {label}
            </NavLink>
          ))}
        </div>
      )}

      {/* Projects list */}
      <div style={{ padding: "0 6px", marginBottom: 4, marginTop: projectId ? 8 : 0 }}>
        <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-secondary)", padding: "0 6px", marginBottom: 3 }}>
          Projects
        </div>
        <NavLink
          to="/projects/new"
          style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 6, padding: "5px 6px",
            borderRadius: 5, fontSize: 11, marginBottom: 1,
            color: "var(--color-purple)",
            background: isActive ? "var(--color-background-primary)" : "transparent",
            textDecoration: "none",
          })}
        >
          <Dot color={null} />
          + New project
        </NavLink>
        {projects.slice(0, 6).map((p) => (
          <NavLink
            key={p.id}
            to={`/projects/${p.id}/dashboard`}
            style={({ isActive }) => ({
              display: "flex", alignItems: "center", gap: 6, padding: "5px 6px",
              borderRadius: 5, fontSize: 11, marginBottom: 1,
              background: isActive || p.id === projectId ? "var(--color-background-primary)" : "transparent",
              color: isActive || p.id === projectId ? "var(--color-text-primary)" : "var(--color-text-secondary)",
              fontWeight: isActive || p.id === projectId ? 500 : 400,
              textDecoration: "none",
            })}
          >
            <Dot color={p.is_active ? "green" : null} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {p.name}
            </span>
          </NavLink>
        ))}
      </div>

      {/* Admin */}
      <div style={{ marginTop: "auto", padding: "8px 6px", borderTop: "0.5px solid var(--color-border-tertiary)" }}>
        <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-secondary)", padding: "0 6px", marginBottom: 3 }}>
          Admin
        </div>
        <NavLink
          to="/admin"
          style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 6, padding: "5px 6px",
            borderRadius: 5, fontSize: 11,
            background: isActive ? "var(--color-background-primary)" : "transparent",
            color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
            textDecoration: "none",
          })}
        >
          <Dot color="amber" />
          Admin Panel
        </NavLink>
      </div>
    </aside>
  );
}
