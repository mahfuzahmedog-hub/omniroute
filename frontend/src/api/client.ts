// Thin typed wrapper over the Forge control-plane API.
//
// It attaches the bearer token, targets the versioned `/api/v1` prefix, and unwraps the
// standardized error envelope ({ error: { code, message, ... } }) into a typed ApiError.

const API_BASE = "/api/v1";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
  correlation_id?: string;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  role: string | null;
}

export type ProjectStatus = "draft" | "active" | "paused" | "archived";

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  specification: string | null;
  status: ProjectStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Health {
  status: string;
  version: string;
  environment: string;
  database: string;
}

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: URLSearchParams } = {}
): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = options.form.toString();
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
  });

  if (resp.status === 204) {
    return undefined as T;
  }

  const payload = await resp.json().catch(() => null);
  if (!resp.ok) {
    const errorBody: ApiErrorBody =
      payload && payload.error
        ? payload.error
        : { code: "unknown", message: `Request failed (${resp.status})` };
    throw new ApiError(resp.status, errorBody);
  }
  return payload as T;
}

export const api = {
  health: () => request<Health>("/health"),

  register: (email: string, password: string, fullName?: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: { email, password, full_name: fullName || null },
    }),

  login: (email: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return request<TokenResponse>("/auth/login", { method: "POST", form });
  },

  me: () => request<User>("/auth/me"),

  listWorkspaces: () => request<Workspace[]>("/workspaces"),

  listProjects: (workspaceId: string, limit = 20, offset = 0) =>
    request<Page<Project>>(
      `/workspaces/${workspaceId}/projects?limit=${limit}&offset=${offset}`
    ),

  createProject: (
    workspaceId: string,
    input: { name: string; slug: string; specification?: string }
  ) =>
    request<Project>(`/workspaces/${workspaceId}/projects`, {
      method: "POST",
      body: input,
    }),
};
