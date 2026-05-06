import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listProjects } from "../api/client";

function StatusDot({ active }) {
  return (
    <div style={{
      width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
      background: active ? "var(--color-green)" : "var(--color-border-secondary)",
    }} />
  );
}

function ProjectCard({ project }) {
  return (
    <Link
      to={`/projects/${project.id}/dashboard`}
      style={{
        display: "block",
        background: "var(--color-background-primary)",
        border: "0.5px solid var(--color-border-tertiary)",
        borderRadius: 6, padding: "10px 12px",
        textDecoration: "none",
        transition: "border-color 0.12s",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--color-border-primary)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--color-border-tertiary)"; }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <StatusDot active={project.is_active} />
            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--color-text-primary)" }}>
              {project.name}
            </span>
          </div>
          <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
            {project.keywords?.slice(0, 4).map((kw) => (
              <span key={kw} style={{
                fontSize: 9, padding: "1px 5px", borderRadius: 3,
                background: "var(--color-blue-bg)", color: "var(--color-blue-text)",
              }}>{kw}</span>
            ))}
            {project.keywords?.length > 4 && (
              <span style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
                +{project.keywords.length - 4}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 14, paddingTop: 8, borderTop: "0.5px solid var(--color-border-tertiary)" }}>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
          <span style={{ fontWeight: 500, color: "var(--color-text-primary)", fontSize: 11 }}>
            {project.post_count?.toLocaleString() || 0}
          </span> posts
        </div>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)" }}>
          <span style={{
            fontWeight: 500, fontSize: 11,
            color: project.signal_count > 0 ? "var(--color-red-text)" : "var(--color-text-primary)",
          }}>
            {project.signal_count || 0}
          </span> signals
        </div>
        <div style={{ fontSize: 9, color: "var(--color-text-secondary)", marginLeft: "auto" }}>
          {project.sources?.join(", ")}
        </div>
      </div>
    </Link>
  );
}

export default function ProjectList() {
  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchInterval: 30000,
  });

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", overflow: "hidden" }}>
      {/* Topbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        borderBottom: "0.5px solid var(--color-border-tertiary)", flexShrink: 0,
      }}>
        <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>Projects</span>
        <Link
          to="/projects/new"
          style={{
            fontSize: 10, padding: "3px 8px", borderRadius: 4,
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-primary)", fontWeight: 500,
          }}
        >
          + New project
        </Link>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: 12 }}>
        {isLoading && (
          <div style={{ fontSize: 10, color: "var(--color-text-secondary)", padding: "20px 0" }}>
            Loading projects…
          </div>
        )}

        {error && (
          <div style={{
            background: "var(--color-red-bg)",
            border: "0.5px solid var(--color-red)",
            borderRadius: 6, padding: "10px 12px",
            fontSize: 10, color: "var(--color-red-text)", marginBottom: 16,
          }}>
            Failed to load projects. Is the backend running?
          </div>
        )}

        {!isLoading && projects.length === 0 && (
          <div style={{
            textAlign: "center", padding: "60px 0",
            border: "0.5px dashed var(--color-border-secondary)",
            borderRadius: "var(--border-radius-lg)", margin: "20px 0",
          }}>
            <div style={{ fontSize: 22, marginBottom: 8 }}>⚡</div>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>No projects yet</div>
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 16 }}>
              Create your first monitoring project to start capturing social signals.
            </div>
            <Link
              to="/projects/new"
              style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                fontSize: 11, padding: "5px 14px", borderRadius: 5,
                border: "0.5px solid var(--color-border-primary)",
                background: "var(--color-background-secondary)",
                color: "var(--color-text-primary)", fontWeight: 500,
              }}
            >
              + Create project
            </Link>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
          {projects.map((p) => <ProjectCard key={p.id} project={p} />)}
        </div>
      </div>
    </div>
  );
}
