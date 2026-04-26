import { ReactNode, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import SchedulerDashboard from "./pages/SchedulerDashboard";
import Overview from "./pages/Overview";
import StoreDetail from "./pages/StoreDetail";
import QualityFeedback from "./pages/QualityFeedback";
import StoreAdmin from "./pages/StoreAdmin";

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
        if (active) {
          setStatus("authenticated");
        }
      })
      .catch(() => {
        localStorage.removeItem("iris_token");
        if (active) {
          setStatus("unauthenticated");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  if (status === "checking") {
    return <AuthLoading />;
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }
  return <AppLayout>{children}</AppLayout>;
}

function LoginRoute() {
  const [status, setStatus] = useState<"checking" | "ready" | "redirect">("checking");

  useEffect(() => {
    const token = localStorage.getItem("iris_token");
    if (!token) {
      setStatus("ready");
      return;
    }

    let active = true;
    getMe()
      .then(() => {
        if (active) {
          setStatus("redirect");
        }
      })
      .catch(() => {
        localStorage.removeItem("iris_token");
        if (active) {
          setStatus("ready");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  if (status === "checking") {
    return <AuthLoading />;
  }
  if (status === "redirect") {
    return <Navigate to="/overview" replace />;
  }
  return <Login />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="/scheduler"
          element={
            <RequireAuth>
              <SchedulerDashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/overview"
          element={
             <RequireAuth>
               <Overview />
             </RequireAuth>
          }
        />
        <Route
          path="/detail"
          element={
             <RequireAuth>
               <StoreDetail />
             </RequireAuth>
          }
        />
        <Route
          path="/quality"
          element={
             <RequireAuth>
               <QualityFeedback />
             </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
             <RequireAuth>
               <StoreAdmin />
             </RequireAuth>
          }
        />
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
