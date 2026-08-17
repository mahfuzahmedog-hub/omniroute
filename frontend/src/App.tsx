import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { NAV_AREAS } from "./nav";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Projects from "./pages/Projects";
import Settings from "./pages/Settings";
import Placeholder from "./pages/Placeholder";

export default function App() {
  const { token, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">Loading…</div>
    );
  }

  if (!token) {
    return <Login />;
  }

  // Areas whose subsystems are not built yet render an honest placeholder page.
  const placeholderAreas = NAV_AREAS.filter((area) => !area.implemented);

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/settings" element={<Settings />} />
        {placeholderAreas.map((area) => (
          <Route
            key={area.key}
            path={area.path}
            element={<Placeholder title={area.label} phase={area.phase} />}
          />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
