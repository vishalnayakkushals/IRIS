import { ReactNode, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import SchedulerDashboard from "./pages/SchedulerDashboard";
import Overview from "./pages/Overview";
import StoreDetail from "./pages/StoreDetail";
import QualityFeedback from "./pages/QualityFeedback";
import RunDetail from "./pages/RunDetail";
import ReportsPage from "./pages/ReportsPage";
import CustomerJourneys from "./pages/CustomerJourneys";
import StoreMapping from "./pages/StoreMapping";
import CameraZones from "./pages/CameraZones";
import EmployeeManagement from "./pages/EmployeeManagement";
import Organisation from "./pages/Organisation";
import UsersPage from "./pages/UsersPage";
import RolePermissions from "./pages/RolePermissions";
import StoreAccess from "./pages/StoreAccess";
import ModelAccuracy from "./pages/ModelAccuracy";
import ActivityLogs from "./pages/ActivityLogs";
import StoreMaster from "./pages/StoreMaster";

import { AppLayout } from "./components/layout/AppLayout";
import { getMe } from "./api/client";

function AuthLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-600">
      <div className="rounded-lg border bg-white px-5 py-3 shadow-sm">
        Checking your session...
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
  return <AppLayout>{children}</AppLayout>;
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
  return <RequireAuth>{el}</RequireAuth>;
}

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
