import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import SchedulerDashboard from "./pages/SchedulerDashboard";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("iris_token");
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
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
        <Route path="/" element={<Navigate to="/scheduler" replace />} />
        <Route path="*" element={<Navigate to="/scheduler" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
