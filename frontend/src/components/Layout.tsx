import { NavLink } from "react-router-dom";
import { NAV_AREAS } from "../nav";
import { useAuth } from "../auth/AuthContext";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen flex bg-forge-bg text-gray-200">
      <aside className="w-60 shrink-0 border-r border-forge-border bg-forge-panel flex flex-col">
        <div className="px-4 py-4 border-b border-forge-border">
          <div className="text-lg font-semibold flex items-center gap-2">
            <span aria-hidden>⚒️</span> Forge
          </div>
          <div className="text-xs text-gray-500">Command Center</div>
        </div>
        <nav className="flex-1 overflow-y-auto py-2" aria-label="Primary">
          {NAV_AREAS.map((area) => (
            <NavLink
              key={area.key}
              to={area.path}
              end={area.path === "/"}
              className={({ isActive }) =>
                [
                  "flex items-center justify-between px-4 py-2 text-sm",
                  isActive
                    ? "bg-forge-bg text-white border-l-2 border-forge-accent"
                    : "text-gray-400 hover:text-gray-200 hover:bg-forge-bg/50 border-l-2 border-transparent",
                ].join(" ")
              }
            >
              <span>{area.label}</span>
              {!area.implemented && (
                <span className="text-[10px] uppercase tracking-wide text-gray-600">
                  P{area.phase}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-forge-border px-4 py-3 text-xs">
          <div className="truncate text-gray-300">{user?.email}</div>
          <button
            onClick={logout}
            className="mt-2 text-forge-accent hover:underline"
            type="button"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
