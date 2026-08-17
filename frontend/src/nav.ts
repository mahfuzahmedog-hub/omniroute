// The command-center navigation, mirroring spec 21_UI's primary navigation.
//
// Each area maps to a build phase. Areas outside Phase 1 render an honest
// "planned" placeholder rather than pretending to work — the master spec forbids
// presenting placeholder functionality as complete.

export interface NavArea {
  key: string;
  label: string;
  path: string;
  phase: number;
  implemented: boolean;
}

export const NAV_AREAS: NavArea[] = [
  { key: "overview", label: "Command Center", path: "/", phase: 1, implemented: true },
  { key: "projects", label: "Projects", path: "/projects", phase: 1, implemented: true },
  { key: "agents", label: "Agents", path: "/agents", phase: 3, implemented: false },
  { key: "tasks", label: "Tasks", path: "/tasks", phase: 2, implemented: false },
  { key: "research", label: "Research", path: "/research", phase: 6, implemented: false },
  { key: "code", label: "Code", path: "/code", phase: 6, implemented: false },
  { key: "files", label: "Files", path: "/files", phase: 5, implemented: false },
  { key: "terminal", label: "Terminal", path: "/terminal", phase: 4, implemented: false },
  { key: "browser", label: "Browser", path: "/browser", phase: 7, implemented: false },
  { key: "tests", label: "Tests", path: "/tests", phase: 7, implemented: false },
  { key: "memory", label: "Memory", path: "/memory", phase: 9, implemented: false },
  { key: "graph", label: "Knowledge Graph", path: "/graph", phase: 9, implemented: false },
  { key: "git", label: "Git", path: "/git", phase: 6, implemented: false },
  { key: "deployments", label: "Deployments", path: "/deployments", phase: 11, implemented: false },
  { key: "costs", label: "Costs", path: "/costs", phase: 10, implemented: false },
  { key: "logs", label: "Logs", path: "/logs", phase: 8, implemented: false },
  { key: "settings", label: "Settings", path: "/settings", phase: 1, implemented: true },
];
