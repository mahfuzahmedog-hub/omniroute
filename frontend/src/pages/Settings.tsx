import { useAuth } from "../auth/AuthContext";

export default function Settings() {
  const { user } = useAuth();
  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">Settings</h1>
      <section className="mt-6 rounded-lg border border-forge-border bg-forge-panel p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Account</h2>
        <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <dt className="text-gray-500">Email</dt>
          <dd className="text-gray-200">{user?.email}</dd>
          <dt className="text-gray-500">Name</dt>
          <dd className="text-gray-200">{user?.full_name || "—"}</dd>
          <dt className="text-gray-500">User ID</dt>
          <dd className="font-mono text-xs text-gray-400">{user?.id}</dd>
        </dl>
      </section>
    </div>
  );
}
