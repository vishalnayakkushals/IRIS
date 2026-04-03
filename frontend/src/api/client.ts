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
