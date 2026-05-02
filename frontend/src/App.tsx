import { ReactNode, Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/layout/AppLayout";
import { StoreProvider } from "./context/StoreContext";
import { getMe } from "./api/client";

const Login = lazy(() => import("./pages/Login"));
const SchedulerDashboard = lazy(() => import("./pages/SchedulerDashboard"));
const Overview = lazy(() => import("./pages/Overview"));
const StoreDetail = lazy(() => import("./pages/StoreDetail"));
const QualityFeedback = lazy(() => import("./pages/QualityFeedback"));
const RunDetail = lazy(() => import("./pages/RunDetail"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const CustomerJourneys = lazy(() => import("./pages/CustomerJourneys"));
const StoreMapping = lazy(() => import("./pages/StoreMapping"));
const CameraZones = lazy(() => import("./pages/CameraZones"));
const EmployeeManagement = lazy(() => import("./pages/EmployeeManagement"));
const Organisation = lazy(() => import("./pages/Organisation"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const RolePermissions = lazy(() => import("./pages/RolePermissions"));
const StoreAccess = lazy(() => import("./pages/StoreAccess"));
const ModelAccuracy = lazy(() => import("./pages/ModelAccuracy"));
const ActivityLogs = lazy(() => import("./pages/ActivityLogs"));
const StoreMaster = lazy(() => import("./pages/StoreMaster"));
const FrameReview = lazy(() => import("./pages/FrameReview"));
const ModelFeedback = lazy(() => import("./pages/ModelFeedback"));

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

function RequireAuth({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"checking" | "authenticated" | "unauthenticated">("checking");

  useEffect(() => {
    const token = localStorage.getItem("iris_token");
    if (!token) {
      setStatus("unauthenticated");
      return;
    }

    let active = true;
    getMe()
      .then(() => {
        if (active) setStatus("authenticated");
      })
      .catch(() => {
        localStorage.removeItem("iris_token");
        if (active) setStatus("unauthenticated");
      });

    return () => { active = false; };
  }, []);

  if (status === "checking") return <AuthLoading />;
  if (status === "unauthenticated") return <Navigate to="/login" replace />;
  return <StoreProvider><AppLayout>{children}</AppLayout></StoreProvider>;
}

function LoginRoute() {
  const [status, setStatus] = useState<"checking" | "ready" | "redirect">("checking");

  useEffect(() => {
    const token = localStorage.getItem("iris_token");
    if (!token) { setStatus("ready"); return; }

    let active = true;
    getMe()
      .then(() => { if (active) setStatus("redirect"); })
      .catch(() => {
        localStorage.removeItem("iris_token");
        if (active) setStatus("ready");
      });

    return () => { active = false; };
  }, []);

  if (status === "checking") return <AuthLoading />;
  if (status === "redirect") return <Navigate to="/overview" replace />;
  return <Login />;
}

function auth(el: ReactNode) {
  return (
    <RequireAuth>
      <Suspense fallback={<RouteLoading />}>{el}</Suspense>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<AuthLoading />}>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />

          {/* Core */}
          <Route path="/overview" element={auth(<Overview />)} />
          <Route path="/detail" element={auth(<StoreDetail />)} />
          <Route path="/quality" element={auth(<QualityFeedback />)} />
          <Route path="/scheduler" element={auth(<SchedulerDashboard />)} />
          <Route path="/runs/:runId" element={auth(<RunDetail />)} />

          {/* Reports */}
          <Route path="/reports" element={auth(<ReportsPage />)} />
          <Route path="/journeys" element={auth(<CustomerJourneys />)} />

          {/* QA */}
          <Route path="/qa/frame-review" element={auth(<FrameReview />)} />
          <Route path="/qa/model-feedback" element={auth(<ModelFeedback />)} />

          {/* Admin */}
          <Route path="/admin/stores" element={auth(<StoreMapping />)} />
          <Route path="/admin/store-master" element={auth(<StoreMaster />)} />
          <Route path="/admin/cameras" element={auth(<CameraZones />)} />
          <Route path="/admin/employees" element={auth(<EmployeeManagement />)} />
          <Route path="/admin/users" element={auth(<UsersPage />)} />
          <Route path="/admin/roles" element={auth(<RolePermissions />)} />
          <Route path="/admin/store-access" element={auth(<StoreAccess />)} />
          <Route path="/admin/organisation" element={auth(<Organisation />)} />
          <Route path="/admin/model-accuracy" element={auth(<ModelAccuracy />)} />
          <Route path="/admin/activity" element={auth(<ActivityLogs />)} />

          {/* Legacy redirect — old /admin path goes to store mapping */}
          <Route path="/admin" element={<Navigate to="/admin/stores" replace />} />

          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
