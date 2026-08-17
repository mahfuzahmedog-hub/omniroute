import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Project, type Workspace } from "../api/client";

export default function Projects() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [spec, setSpec] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .listWorkspaces()
      .then((ws) => {
        setWorkspaces(ws);
        if (ws.length > 0) setWorkspaceId(ws[0].id);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    setError(null);
    api
      .listProjects(workspaceId)
      .then((page) => setProjects(page.items))
      .catch((e) => setError(e.message));
  }, [workspaceId]);

  const canSubmit = useMemo(
    () => name.trim().length > 0 && /^[a-z0-9][a-z0-9-]*$/.test(slug) && !submitting,
    [name, slug, submitting]
  );

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!workspaceId) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await api.createProject(workspaceId, {
        name: name.trim(),
        slug: slug.trim(),
        specification: spec.trim() || undefined,
      });
      setProjects((prev) => [project, ...prev]);
      setName("");
      setSlug("");
      setSpec("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <p className="text-gray-400">Loading…</p>;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-white">Projects</h1>
        {workspaces.length > 1 && (
          <select
            className="rounded border border-forge-border bg-forge-panel px-2 py-1 text-sm"
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
          >
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id}>
                {ws.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <p className="mt-4 text-red-400">{error}</p>}

      <form
        onSubmit={handleCreate}
        className="mt-6 space-y-3 rounded-lg border border-forge-border bg-forge-panel p-4"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          New project
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            className="rounded border border-forge-border bg-forge-bg px-3 py-2 text-sm"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="rounded border border-forge-border bg-forge-bg px-3 py-2 text-sm"
            placeholder="slug (a-z, 0-9, hyphens)"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
        </div>
        <textarea
          className="w-full rounded border border-forge-border bg-forge-bg px-3 py-2 text-sm"
          placeholder="Specification (the goal you want Forge to build)"
          rows={3}
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded bg-forge-accent px-4 py-2 text-sm font-medium text-black disabled:opacity-40"
        >
          {submitting ? "Creating…" : "Create project"}
        </button>
      </form>

      <ul className="mt-6 space-y-2">
        {projects.length === 0 && <li className="text-gray-500">No projects yet.</li>}
        {projects.map((p) => (
          <li
            key={p.id}
            className="flex items-center justify-between rounded-lg border border-forge-border bg-forge-panel px-4 py-3"
          >
            <div>
              <div className="font-medium text-white">{p.name}</div>
              <div className="text-xs text-gray-500">{p.slug}</div>
            </div>
            <span className="rounded-full border border-forge-border px-2 py-0.5 text-xs text-gray-400">
              {p.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
