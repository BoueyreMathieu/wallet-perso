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
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  del: <T = void>(p: string) => request<T>("DELETE", p),
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

export interface Category {
  id: number;
  parent_id: number | null;
  name: string;
  kind: "depense" | "revenu" | "transfert";
  color: string | null;
}

export interface Transaction {
  id: number;
  account_id: number;
  account_name: string;
  booked_at: string;
  amount_cents: number;
  label: string;
  raw_label: string;
  merchant_id: number | null;
  merchant: string | null;
  category_id: number | null;
  category_locked: boolean;
  is_transfer: boolean;
  note: string | null;
  counted: boolean;
  linked_id: number | null;
  status: string | null;
  details: Record<string, string> | null;
  rule_id: number | null;
  source: string;
  tags: TagRef[];
}

export interface TagRef {
  id: number;
  name: string;
  color: string | null;
  source: "manuel" | "vendeur" | "service";
}

export interface Tag {
  id: number;
  name: string;
  color: string | null;
  transactions: number;
  spent_cents: number;
  merchants: number;
  services: number;
}

export interface Service {
  id: number;
  merchant_id: number;
  label: string | null;
  pattern: string;
  match_type: "contient" | "regex";
  amount_min_cents: number | null;
  amount_max_cents: number | null;
  category_id: number | null;
  tag_ids: number[];
}

export interface Share {
  category_id?: number | null;
  rule_id?: number | null;
  label?: string;
  count: number;
  spent_cents: number;
  received_cents: number;
}

export interface MerchantGroup {
  merchant_id: number | null;
  merchant: string | null;
  count: number;
  total_cents: number;
  last_date: string;
  sample_label: string;
}

export interface ImportResult {
  account_id: number;
  account_name: string;
  rows_total: number;
  imported: number;
  skipped: number;
  updated: number;
  categorized: number;
  reconciled: number;
  merged_manual: number;
  period_start: string | null;
  period_end: string | null;
  balance_cents: number | null;
  balance_date: string | null;
}

/** Envoi d'un fichier (multipart). */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", body: form, credentials: "same-origin" });
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
  return res.json();
}

export interface MerchantStats {
  id: number;
  name: string;
  category_id: number | null;
  category_chosen: boolean;
  categories: Share[];
  services: number;
  tag_ids: number[];
  count: number;
  spent_cents: number;
  received_cents: number;
  last_date: string | null;
}

export interface ImportBatch {
  id: number;
  source: string;
  filename: string | null;
  account_id: number | null;
  account_name: string | null;
  started_at: string;
  rows_total: number;
  rows_imported: number;
}

export interface ServiceSuggestion {
  pattern: string;
  label: string;
  matches: number;
  amount_cents: number;
}
