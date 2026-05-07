import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  headers: { "Content-Type": "application/json" },
});

// ─── Projects ─────────────────────────────────────────────────────────────────
export const createProject = (data) => api.post("/projects", data).then((r) => r.data);
export const listProjects = () => api.get("/projects").then((r) => r.data);
export const getProject = (id) => api.get(`/projects/${id}`).then((r) => r.data);
export const updateProject = (id, data) => api.patch(`/projects/${id}`, data).then((r) => r.data);
export const deleteProject = (id) => api.delete(`/projects/${id}`);
export const triggerScrape = (id) => api.post(`/projects/${id}/scrape`).then((r) => r.data);
export const pauseProject = (id) => api.post(`/projects/${id}/pause`).then((r) => r.data);
export const resumeProject = (id) => api.post(`/projects/${id}/resume`).then((r) => r.data);
export const getDashboardStats = (id) => api.get(`/projects/${id}/stats`).then((r) => r.data);
export const getProjectSources = (id) => api.get(`/projects/${id}/sources`).then((r) => r.data);

// ─── Posts ────────────────────────────────────────────────────────────────────
export const listRawPosts = (projectId, params) =>
  api.get(`/projects/${projectId}/raw-posts`, { params }).then((r) => r.data);
export const listEnrichedPosts = (projectId, params) =>
  api.get(`/projects/${projectId}/posts/enriched`, { params }).then((r) => r.data);

// ─── Signals ─────────────────────────────────────────────────────────────────
export const listSignals = (projectId, params) =>
  api.get(`/projects/${projectId}/signals`, { params }).then((r) => r.data);
export const triageSignal = (signalId, data) =>
  api.post(`/projects/signals/${signalId}/triage`, data).then((r) => r.data);
export const triageSignalWithAI = (signalId) =>
  api.post(`/projects/signals/${signalId}/triage-ai`).then((r) => r.data);

// ─── Pipeline ─────────────────────────────────────────────────────────────────
export const runPipeline = (projectId) =>
  api.get(`/pipeline/run/${projectId}`).then((r) => r.data);

// ─── Canvas ───────────────────────────────────────────────────────────────────
export const getCanvas = (projectId) =>
  api.get(`/projects/${projectId}/canvas`).then((r) => r.data);
export const updateCanvas = (projectId, cards) =>
  api.patch(`/projects/${projectId}/canvas`, { cards }).then((r) => r.data);
export const shareCanvas = (projectId) =>
  api.post(`/projects/${projectId}/canvas/share`).then((r) => r.data);

// ─── Copilot ──────────────────────────────────────────────────────────────────
export const copilotChat = (projectId, data) =>
  api.post(`/projects/${projectId}/copilot`, data).then((r) => r.data);

// ─── Admin ────────────────────────────────────────────────────────────────────
export const getPipelineHealth = () => api.get("/admin/pipeline/health").then((r) => r.data);
export const listPiiQueue = (params) => api.get("/admin/pii-queue", { params }).then((r) => r.data);
export const reviewPiiItem = (id, data) => api.patch(`/admin/pii-queue/${id}`, data).then((r) => r.data);
export const discoverSources = (keyword) =>
  api.post("/admin/discover", { keyword }, { timeout: 60000 }).then((r) => r.data);
export const getAuditLog = (params) => api.get("/admin/audit-log", { params }).then((r) => r.data);

// ─── Global Sources (Reliable Sources Registry) ───────────────────────────────
export const listGlobalSources = () => api.get("/global-sources").then((r) => r.data);
export const addConfirmedSource = (data) => api.post("/global-sources/add-confirmed", data).then((r) => r.data);
export const addCustomSource = (data) => api.post("/global-sources/add-custom", data).then((r) => r.data);
export const toggleGlobalSource = (id, enabled) => api.post(`/global-sources/${id}/toggle`, null, { params: { enabled } }).then((r) => r.data);
export const deleteGlobalSource = (id) => api.delete(`/global-sources/${id}`);
export const probeApi = (data) => api.post("/global-sources/probe-api", data).then((r) => r.data);
export const listSignalReview = (params) => api.get("/admin/signal-review", { params }).then((r) => r.data);
export const getSignalReviewCounts = () => api.get("/admin/signal-review/counts").then((r) => r.data);

// Compliance
export const getComplianceReport = () => api.get("/admin/compliance/report").then((r) => r.data);
export const getComplianceSettings = () => api.get("/admin/compliance/settings").then((r) => r.data);
export const updateComplianceSettings = (data) => api.patch("/admin/compliance/settings", data).then((r) => r.data);
export const runRetentionPurge = () => api.post("/admin/compliance/run-retention").then((r) => r.data);
export const gdprErase = (data) => api.post("/admin/compliance/gdpr-erase", data).then((r) => r.data);
export const getRbacModel = () => api.get("/admin/compliance/rbac-model").then((r) => r.data);

export default api;
