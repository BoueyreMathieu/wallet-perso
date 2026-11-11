export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* réponse sans JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: (p: string) => request<void>("DELETE", p),
};

export type AccountType = "courant" | "epargne" | "investissement" | "paypal" | "especes" | "credit" | "bien";

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  institution: string | null;
  currency: string;
  include_in_net_worth: boolean;
  is_archived: boolean;
  provider: string;
  balance_cents: number | null;
  balance_date: string | null;
}

export interface NetWorth {
  total_cents: number;
  by_type: Record<string, number>;
}
