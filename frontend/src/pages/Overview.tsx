import { useEffect, useState } from "react";
import { api, type Health, type Workspace } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function Overview() {
  const { user } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.listWorkspaces()])
      .then(([h, ws]) => {
        setHealth(h);
        setWorkspaces(ws);
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">Command Center</h1>
      <p className="mt-1 text-gray-400">
        Welcome back, {user?.full_name || user?.email}.
      </p>

      {error && <p className="mt-4 text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="API status" value={health?.status ?? "…"} accent={health?.status === "ok"} />
        <Stat label="Database" value={health?.database ?? "…"} accent={health?.database === "ok"} />
        <Stat label="Workspaces" value={String(workspaces.length)} />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Environment
        </h2>
        <div className="mt-2 rounded-lg border border-forge-border bg-forge-panel p-4 text-sm text-gray-300">
          <div>Version: {health?.version ?? "unknown"}</div>
          <div>Environment: {health?.environment ?? "unknown"}</div>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-forge-border bg-forge-panel p-4">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${accent ? "text-green-400" : "text-white"}`}>
        {value}
      </div>
    </div>
  );
}
