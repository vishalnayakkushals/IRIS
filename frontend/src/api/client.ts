import axios from "axios";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

export const api = axios.create({ baseURL: BASE });

// Attach Bearer token on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("iris_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-logout on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("iris_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/login", { email, password });

export const getMe = () =>
  api.get<{ email: string; full_name: string; store_id: string }>("/auth/me");

// ── Jobs ─────────────────────────────────────────────────────────────────────
export interface JobStatus {
  key: string;
  name: string;
  status: "idle" | "queued" | "running" | "done" | "failed";
  remarks: string;
  last_run_at: string | null;
  triggered_by: string | null;
  run_id: string | null;
}

export const getJobs = () => api.get<JobStatus[]>("/jobs");

export const triggerAll = () =>
  api.post<{ run_id: string; message: string }>("/jobs/trigger-all");

export const triggerJob = (key: string) =>
  api.post<{ run_id: string; message: string }>(`/jobs/${key}/trigger`);

// ── Runs ─────────────────────────────────────────────────────────────────────
export interface RunRecord {
  run_id: string;
  job_key: string;
  job_name: string;
  store_id: string;
  status: string;
  remarks: string;
  triggered_by: string;
  started_at: string;
  completed_at: string;
  created_at: string;
}

export const getRuns = (limit = 50) =>
  api.get<{ runs: RunRecord[]; total: number }>(`/runs?limit=${limit}`);

// ── Dashboard ────────────────────────────────────────────────────────────────
export const fetchOverview = () =>
  api.get("/dashboard/overview");

export interface TrafficPoint {
  date: string;
  total: number;
  customers: number;
  staff: number;
  conversions: number;
}

export const fetchTraffic = (storeId?: string, days = 30) =>
  api.get<{ series: TrafficPoint[]; store_id: string; days: number }>(
    `/dashboard/traffic?days=${days}${storeId ? `&store_id=${storeId}` : ""}`
  );

export const fetchDashboardRuns = (limit = 50) =>
  api.get<{ runs: RunRecord[]; total: number }>(`/dashboard/pipeline-runs?limit=${limit}`);

// ── Stores ───────────────────────────────────────────────────────────────────
export interface StoreOption {
  store_id: string;
  store_name: string;
  email: string;
}

export const listStores = () =>
  api.get<{ stores: StoreOption[]; total: number }>("/detail/stores");

export const fetchStoreMetrics = (storeId: string) =>
  api.get(`/detail/${storeId}/metrics`);

// ── Walk-in Sessions ─────────────────────────────────────────────────────────
export interface WalkinSession {
  id: number;
  store_id: string;
  walkin_id: string;
  group_id: string;
  role: string;
  date: string;
  entry_time: string;
  exit_time: string;
  time_spent_mins: string;
  session_status: string;
  entry_type: string;
  gender: string;
  age_band: string;
  clothing_style_archetype: string;
  engagement_type: string;
  engagement_depth: string;
  purchase_signal_bag: string;
  included_in_analytics: string;
  created_at: string;
}

export const fetchWalkins = (storeId?: string, limit = 200) =>
  storeId
    ? api.get<{ sessions: WalkinSession[]; total: number }>(`/detail/${storeId}/walkins?limit=${limit}`)
    : api.get<{ sessions: WalkinSession[]; total: number }>(`/detail/walkins?limit=${limit}`);

// ── Admin — Stores ────────────────────────────────────────────────────────────
export const adminListStores = () => api.get<any[]>("/admin/stores");
export const adminCreateStore = (body: any) => api.post("/admin/stores", body);
export const adminUpdateStore = (id: string, body: any) => api.put(`/admin/stores/${id}`, body);
export const adminDeleteStore = (id: string) => api.delete(`/admin/stores/${id}`);
export const adminToggleStoreSync = (id: string, body: { sync_enabled: boolean; sync_interval_hours?: number }) =>
  api.put(`/admin/stores/${id}/sync`, body);

// ── Admin — Users ─────────────────────────────────────────────────────────────
export const adminListUsers = () => api.get<any[]>("/admin/users");
export const adminCreateUser = (body: any) => api.post("/admin/users", body);
export const adminUpdateUser = (email: string, body: any) => api.put(`/admin/users/${encodeURIComponent(email)}`, body);
export const adminDeleteUser = (email: string) => api.delete(`/admin/users/${encodeURIComponent(email)}`);
export const adminResetPassword = (email: string, new_password: string) =>
  api.post(`/admin/users/${encodeURIComponent(email)}/password`, { new_password });

// ── Admin — Roles ─────────────────────────────────────────────────────────────
export const adminListRoles = () => api.get<any[]>("/admin/roles");
export const adminCreateRole = (body: any) => api.post("/admin/roles", body);
export const adminDeleteRole = (name: string) => api.delete(`/admin/roles/${encodeURIComponent(name)}`);
export const adminSetPermissions = (role: string, perms: any[]) =>
  api.put(`/admin/roles/${encodeURIComponent(role)}/permissions`, perms);
export const adminListPermissionCodes = () => api.get<string[]>("/admin/permissions/codes");

// ── Admin — Settings ──────────────────────────────────────────────────────────
export const adminGetSettings = () => api.get<Record<string, string>>("/admin/settings");
export const adminUpdateSettings = (body: Record<string, string>) => api.put("/admin/settings", body);

// ── Admin — Employees ─────────────────────────────────────────────────────────
export const adminListEmployees = (storeId: string) => api.get<any[]>(`/admin/employees/${storeId}`);
export const adminDeleteEmployee = (storeId: string, id: number) =>
  api.delete(`/admin/employees/${storeId}/${id}`);

// ── Admin — Cameras ───────────────────────────────────────────────────────────
export const adminListCameras = (storeId: string) => api.get<any[]>(`/admin/cameras/${storeId}`);
export const adminUpsertCamera = (storeId: string, body: any) => api.post(`/admin/cameras/${storeId}`, body);
export const adminDeleteCamera = (storeId: string, cameraId: string) =>
  api.delete(`/admin/cameras/${storeId}/${encodeURIComponent(cameraId)}`);

// ── Admin — Locations ─────────────────────────────────────────────────────────
export const adminListLocations = (storeId: string) => api.get<any[]>(`/admin/locations/${storeId}`);
export const adminUpsertLocation = (storeId: string, body: any) => api.post(`/admin/locations/${storeId}`, body);
export const adminDeleteLocation = (storeId: string, floor: string, location: string) =>
  api.delete(`/admin/locations/${storeId}?floor_name=${encodeURIComponent(floor)}&location_name=${encodeURIComponent(location)}`);

// ── Admin — Store Access ──────────────────────────────────────────────────────
export const adminGetStoreAccess = (email: string) => api.get<any[]>(`/admin/store-access/${encodeURIComponent(email)}`);
export const adminReplaceStoreAccess = (email: string, store_ids: string[]) =>
  api.post(`/admin/store-access/${encodeURIComponent(email)}`, { store_ids });

// ── Admin — Activity Log ──────────────────────────────────────────────────────
export const adminListActivity = (actor?: string, limit = 100) =>
  api.get<any[]>(`/admin/activity?limit=${limit}${actor ? `&actor_email=${encodeURIComponent(actor)}` : ""}`);

// ── Admin — Store Master ──────────────────────────────────────────────────────
export const adminListStoreMaster = () => api.get<any[]>("/admin/store-master");
export const adminUpsertStoreMaster = (rows: any[]) => api.post("/admin/store-master", rows);
export const adminDeleteStoreMaster = (storeId: string) => api.delete(`/admin/store-master/${storeId}`);
export const adminUploadStoreMasterFile = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/admin/store-master/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

// ── Reports ───────────────────────────────────────────────────────────────────
export const reportsWalkins = (storeId?: string, date?: string, limit = 200) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (storeId) params.set("store_id", storeId);
  if (date) params.set("business_date", date);
  return api.get<any[]>(`/reports/walkins?${params}`);
};
export const reportsSummary = (storeId?: string, limit = 90) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (storeId) params.set("store_id", storeId);
  return api.get<any[]>(`/reports/summary?${params}`);
};
export const reportsImageScans = (storeId?: string, date?: string, limit = 200) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (storeId) params.set("store_id", storeId);
  if (date) params.set("business_date", date);
  return api.get<any[]>(`/reports/image-scans?${params}`);
};
export const reportsModelAccuracy = () => api.get<any[]>("/reports/model-accuracy");
export const reportsStoresWithData = () => api.get<any[]>("/reports/stores-with-data");

// ── On-fly pipeline (no Celery) ───────────────────────────────────────────────
export const onFlyListStores = () => api.get<any[]>("/onfly/stores");
export const onFlyStoreStatus = (storeId: string) => api.get<any>(`/onfly/status/${storeId}`);
export const onFlySync = (storeId: string, body: { gpt_enabled?: boolean; use_tracker?: boolean }) =>
  api.post<any>(`/onfly/sync/${storeId}`, body);
export const onFlyLiveProgress = (storeId: string) => api.get<any>(`/onfly/live-progress/${storeId}`);
export const onFlyDateReport = (storeId: string) => api.get<any[]>(`/onfly/date-report/${storeId}`);

// ── QA Feedback ───────────────────────────────────────────────────────────────
export const qaListFeedback = (storeId?: string, reviewStatus?: string, limit = 200) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (storeId) params.set("store_id", storeId);
  if (reviewStatus) params.set("review_status", reviewStatus);
  return api.get<any[]>(`/qa/feedback?${params}`);
};
export const qaUpdateFeedback = (id: number, body: { review_status: string; corrected_label?: string; comment?: string }) =>
  api.put(`/qa/feedback/${id}`, body);
export const qaDeleteFeedback = (id: number) => api.delete(`/qa/feedback/${id}`);
export const qaRetrain = (storeId: string) => api.post<any>(`/qa/retrain/${storeId}`);
export const qaAccuracy = (storeId: string) => api.get<any>(`/qa/accuracy/${storeId}`);
export const qaImageUrl = (path: string) =>
  `${(import.meta.env.VITE_API_URL ?? "/api")}/qa/image?path=${encodeURIComponent(path)}`;
