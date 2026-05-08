import { Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/layout/AppLayout";
import { StoreProvider } from "./context/StoreContext";
import { getMe } from "./api/client";

const Login            = lazy(() => import("./pages/Login"));
const SchedulerDashboard = lazy(() => import("./pages/SchedulerDashboard"));
const Overview         = lazy(() => import("./pages/Overview"));
const StoreDetail      = lazy(() => import("./pages/StoreDetail"));
const QualityFeedback  = lazy(() => import("./pages/QualityFeedback"));
const RunDetail        = lazy(() => import("./pages/RunDetail"));
const ReportsPage      = lazy(() => import("./pages/ReportsPage"));
const CustomerJourneys = lazy(() => import("./pages/CustomerJourneys"));
const StoreMapping     = lazy(() => import("./pages/StoreMapping"));
const CameraZones      = lazy(() => import("./pages/CameraZones"));
const EmployeeManagement = lazy(() => import("./pages/EmployeeManagement"));
const Organisation     = lazy(() => import("./pages/Organisation"));
const UsersPage        = lazy(() => import("./pages/UsersPage"));
const RolePermissions  = lazy(() => import("./pages/RolePermissions"));
const StoreAccess      = lazy(() => import("./pages/StoreAccess"));
const ModelAccuracy    = lazy(() => import("./pages/ModelAccuracy"));
const ActivityLogs     = lazy(() => import("./pages/ActivityLogs"));
const StoreMaster      = lazy(() => import("./pages/StoreMaster"));
const FrameReview      = lazy(() => import("./pages/FrameReview"));
const ModelFeedback    = lazy(() => import("./pages/ModelFeedback"));

// Module-level: persists across route changes within the browser session.
// Prevents calling getMe() on every navigation.
let _authCache: "authenticated" | "unauthenticated" | null = null;

// Called by the 401 interceptor path (window.location.href = '/login') reloads
// the page anyway, but export this so logout handlers can clear it too.
export function clearAuthCache() { _authCache = null; }

function AuthLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-600">
      <div className="rounded-lg border bg-white px-5 py-3 shadow-sm">
        Checking your session...
      </div>
    </div>
  );
}

function RouteLoading() {
  return (
    <div className="min-h-[40vh] flex items-center justify-center text-slate-500">
      <div className="rounded-lg border bg-white px-4 py-3 shadow-sm">
        Loading page...
      </div>
    </div>
  );
}

// ── Single auth shell ─────────────────────────────────────────────────────
// Mounts ONCE for all authenticated routes. StoreProvider + AppLayout are
// stable — they do NOT remount on every navigation. <Outlet /> is the only
// part that changes when the URL changes.
function AuthShell() {
  const [status, setStatus] = useState<"checking" | "authenticated" | "unauthenticated">(() => {
    if (!localStorage.getItem("iris_token")) return "unauthenticated";
    return _authCache ?? "checking";
  });

  useEffect(() => {
    if (status !== "checking") return;
    let active = true;
    getMe()
      .then(() => {
        _authCache = "authenticated";
        if (active) setStatus("authenticated");
      })
      .catch(() => {
        localStorage.removeItem("iris_token");
        _authCache = "unauthenticated";
        if (active) setStatus("unauthenticated");
      });
    return () => { active = false; };
  }, []);

  if (status === "checking") return <AuthLoading />;
  if (status === "unauthenticated") return <Navigate to="/login" replace />;
  return (
    <StoreProvider>
      <AppLayout>
        <Suspense fallback={<RouteLoading />}>
          <Outlet />
        </Suspense>
      </AppLayout>
    </StoreProvider>
  );
}

// ── Login route ───────────────────────────────────────────────────────────
function LoginRoute() {
  const [status, setStatus] = useState<"checking" | "ready" | "redirect">(() => {
    const token = localStorage.getItem("iris_token");
    if (!token) return "ready";
    return _authCache === "authenticated" ? "redirect" : "checking";
  });

  useEffect(() => {
    if (status !== "checking") return;
    let active = true;
    getMe()
      .then(() => {
        _authCache = "authenticated";
        if (active) setStatus("redirect");
      })
      .catch(() => {
        localStorage.removeItem("iris_token");
        if (active) setStatus("ready");
      });
    return () => { active = false; };
  }, []);

  if (status === "checking") return <AuthLoading />;
  if (status === "redirect") return <Navigate to="/overview" replace />;
  return (
    <Suspense fallback={<AuthLoading />}>
      <Login />
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />

        {/* All authenticated routes share one AuthShell — layout mounts once,
            only <Outlet /> swaps on navigation. No repeated getMe() calls. */}
        <Route element={<AuthShell />}>
          {/* Core */}
          <Route path="/overview"   element={<Overview />} />
          <Route path="/detail"     element={<StoreDetail />} />
          <Route path="/quality"    element={<QualityFeedback />} />
          <Route path="/scheduler"  element={<SchedulerDashboard />} />
          <Route path="/runs/:runId" element={<RunDetail />} />

          {/* Reports */}
          <Route path="/reports"    element={<ReportsPage />} />
          <Route path="/journeys"   element={<CustomerJourneys />} />

          {/* QA */}
          <Route path="/qa/frame-review"    element={<FrameReview />} />
          <Route path="/qa/model-feedback"  element={<ModelFeedback />} />

          {/* Admin */}
          <Route path="/admin/stores"        element={<StoreMapping />} />
          <Route path="/admin/store-master"  element={<StoreMaster />} />
          <Route path="/admin/cameras"       element={<CameraZones />} />
          <Route path="/admin/employees"     element={<EmployeeManagement />} />
          <Route path="/admin/users"         element={<UsersPage />} />
          <Route path="/admin/roles"         element={<RolePermissions />} />
          <Route path="/admin/store-access"  element={<StoreAccess />} />
          <Route path="/admin/organisation"  element={<Organisation />} />
          <Route path="/admin/model-accuracy" element={<ModelAccuracy />} />
          <Route path="/admin/activity"      element={<ActivityLogs />} />
          <Route path="/admin"               element={<Navigate to="/admin/stores" replace />} />
        </Route>

        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
