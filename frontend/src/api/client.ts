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
