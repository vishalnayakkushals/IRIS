import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import SchedulerDashboard from "./pages/SchedulerDashboard";
import Overview from "./pages/Overview";
import StoreDetail from "./pages/StoreDetail";
import QualityFeedback from "./pages/QualityFeedback";
import StoreAdmin from "./pages/StoreAdmin";

import { AppLayout } from "./components/layout/AppLayout";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("iris_token");
  if (!token) return <Navigate to="/login" replace />;
  return <AppLayout>{children}</AppLayout>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
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
