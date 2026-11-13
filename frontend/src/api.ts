import { apiBase, authHeader } from "./native";
import { demoActive, demoAnswer } from "./demo/demo"; // DÉMO (voir docs/demo.md)

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Demande le mot de passe à l'utilisateur (fenêtre montée par App) ; null = annulé. */
type PasswordAsker = (message: string) => Promise<string | null>;
let askPassword: PasswordAsker | null = null;
export function setPasswordAsker(fn: PasswordAsker | null) {
  askPassword = fn;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
  } catch {
    return res.statusText; // réponse sans JSON
  }
}

/** DÉMO (voir docs/demo.md) : serveur injoignable → réponse du jeu de données fictif, si l'appli en a un. */
async function fromDemo<T>(method: string, path: string, confirmOffline: boolean, networkError: ApiError): Promise<T> {
  const demo = await demoAnswer(method, path, confirmOffline);
  if (!demo) throw networkError;
  if ("error" in demo) throw new ApiError(0, demo.error);
  return demo.data as T;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const offline = new ApiError(0, "Serveur injoignable (réseau, Tailscale ou serveur éteint ?)");
  if (demoActive()) return fromDemo<T>(method, path, false, offline); // DÉMO
  const send = async (confirm?: string) => {
    try {
      return await fetch(`${apiBase()}/api${path}`, {
        method,
        credentials: "same-origin",
        headers: {
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
          ...authHeader(),
          // encodé : un en-tête HTTP n'accepte pas les accents
          ...(confirm !== undefined ? { "X-Confirm-Password": encodeURIComponent(confirm) } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw offline;
    }
  };

  let res: Response;
  try {
    res = await send();
  } catch (e) {
    if (e === offline) return fromDemo<T>(method, path, true, offline); // DÉMO
    throw e;
  }
  // Action sensible (suppression, remise à zéro…) : le serveur redemande le mot de passe.
  if (res.status === 428 && askPassword) {
    let message = await errorMessage(res);
    for (let attempt = 0; attempt < 3; attempt++) {
      const password = await askPassword(message);
      if (password === null) throw new ApiError(428, "Action annulée.");
      res = await send(password);
      if (res.status !== 403) break;
      message = "Mot de passe incorrect, réessaie.";
    }
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
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
  pending_cents: number;
  pending_count: number;
}

/** Opération « à venir » vue à la banque (pas encore comptabilisée). */
export interface Pending {
  id: number;
  account_id: number;
  account_name: string;
  booked_at: string;
  amount_cents: number;
  label: string;
  raw_label: string;
  category_id: number | null;
}

export interface NetWorth {
  total_cents: number;
  by_type: Record<string, number>;
}

export interface Category {
  id: number;
  parent_id: number | null;
  name: string;
  kind: CategoryKind;
  color: string | null;
  icon: string | null;
  protected: boolean;
  nature: Nature | null;
  nature_effective: Nature | null;
}

export type Nature = "fixe" | "essentiel" | "plaisir";
export const NATURE_LABELS: Record<Nature, string> = {
  fixe: "Charges fixes",
  essentiel: "Dépenses essentielles",
  plaisir: "Plaisirs et envies",
};

export type CategoryKind = "depense" | "revenu" | "transfert";

export interface CategoryUsage {
  id: number;
  transactions: number;
  rules: number;
  merchants: number;
}

export interface CategoryDeleteResult {
  deleted: number;
  transactions: number;
  moved_to: number | null;
  rules: number;
  merchants: number;
  to_categorize: number;
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
  transfer_pair_id: number | null;
  pair_account: string | null;
  recurring_id: number | null;
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
  const res = await fetch(`${apiBase()}/api${path}`, { method: "POST", body: form, credentials: "same-origin", headers: authHeader() });
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

export interface Dashboard {
  month: string;
  period: "month" | "period";
  pending_spent_cents: number;
  saved_cents: number;
  prev_saved_cents: number;
  savings_rate_3m: number | null;
  focus_category_id: number | null;
  transactions: { id: number; booked_at: string; label: string; amount_cents: number; category_id: number | null; account_name: string }[];
  start: string;
  end: string;
  is_current: boolean;
  spent_cents: number;
  income_cents: number;
  prev_spent_same_day_cents: number;
  prev_spent_cents: number;
  prev_income_cents: number;
  prev_income_same_day_cents: number;
  daily_cumulative: number[];
  prev_daily_cumulative: number[];
  by_category: { category_id: number | null; spent_cents: number; prev_spent_cents: number; count: number }[];
  top_expenses: { id: number; booked_at: string; label: string; amount_cents: number; category_id: number | null; account_name: string }[];
  top_merchants: { merchant_id: number | null; name: string; spent_cents: number; count: number }[];
  months: { month: string; income_cents: number; spent_cents: number; saved_cents: number; net_worth_cents: number | null }[];
  savings_rate: number | null;
  todo: {
    backup_warning: string | null;
    recurring_to_confirm: number;
    price_increases: string[];
    budget_alerts: { category_id: number; level: "alerte" | "depasse" }[];
    to_categorize_ops: number;
    to_categorize_merchants: number;
    connections_to_renew: string[];
    connections_in_error: string[];
    last_sync_at: string | null;
  };
}

// --- Prévoir : récurrents, budgets, trésorerie ---------------------------------------------------

export type Frequency = "hebdomadaire" | "mensuel" | "bimestriel" | "trimestriel" | "semestriel" | "annuel";
export const FREQUENCY_LABELS: Record<Frequency, string> = {
  hebdomadaire: "Chaque semaine",
  mensuel: "Chaque mois",
  bimestriel: "Tous les 2 mois",
  trimestriel: "Chaque trimestre",
  semestriel: "Tous les 6 mois",
  annuel: "Chaque année",
};

export interface Recurring {
  id: number;
  label: string;
  merchant_id: number | null;
  merchant: string | null;
  account_id: number | null;
  account_name: string | null;
  category_id: number | null;
  amount_cents: number;
  frequency: Frequency;
  frequency_label: string;
  monthly_cents: number;
  yearly_cents: number;
  next_date: string | null;
  last_date: string | null;
  first_date: string | null;
  occurrences: number;
  total_cents: number;
  status: "suggere" | "actif" | "ignore" | "termine";
  source: "auto" | "manuel";
  kind: "depense" | "revenu" | "virement";
  late_days: number;
  maybe_ended: boolean;
  previous_amount_cents: number | null;
  price_changed_on: string | null;
  price_increase: boolean;
}

export interface RecurringSummary {
  items: Recurring[];
  to_confirm: number;
  monthly_out_cents: number;
  monthly_in_cents: number;
  yearly_out_cents: number;
}

export interface BudgetItem {
  category_id: number;
  budget_cents: number;
  alert_threshold_pct: number;
  spent_cents: number;
  recurring_spent_cents: number;
  expected_recurring_cents: number;
  projected_cents: number;
  trend_cents: number;
  pace_cents: number;
  remaining_cents: number;
  level: "ok" | "alerte" | "depasse";
}

export interface BudgetsOverview {
  month: string;
  is_current: boolean;
  days_in_month: number;
  elapsed_days: number;
  remaining_days: number;
  total_budget_cents: number;
  total_spent_cents: number;
  total_projected_cents: number;
  items: BudgetItem[];
  suggestions: { category_id: number; average_cents: number; suggested_cents: number }[];
}

export interface ForecastEventOut {
  date: string;
  label: string;
  amount_cents: number;
  kind: "depense" | "revenu" | "virement" | "a_venir";
  category_id?: number | null;
  series_id: number | null;
  account_name: string | null;
  status: string | null;
  late?: boolean;
}

export interface ModelChild {
  category_id: number | null;
  layer: Nature;
  trend_cents: number;
  scenario_cents: number;
  direction: "hausse" | "baisse" | "stable";
  budget_cents: number | null;
  target_cents: number | null;
  history: number[];
}

export interface ModelGroup {
  category_id: number | null;
  trend_cents: number;
  scenario_cents: number;
  budget_cents: number | null;
  target_cents: number | null;
  layers: Nature[];
  children: ModelChild[];
}

export interface ModelView {
  months_used: number;
  groups: ModelGroup[];
  layers: Record<Nature, { trend_cents: number; scenario_cents: number }>;
  other_income_cents: number;
  other_income_direction: string;
}

export interface ScenarioIn {
  plaisir_pct: number;
  apply_budgets: boolean;
  targets: Record<string, number>;
  extra_saving_cents: number;
}

export interface ForecastCategory {
  category_id: number | null;
  layer: Nature;
  monthly_cents: number;
  scenario_monthly_cents: number;
  amount_cents: number;
  base_amount_cents: number;
  direction: string;
}

export interface Forecast {
  today: string;
  horizon: string;
  account_ids: number[];
  accounts: string[];
  start_balance_cents: number;
  end_balance_cents: number;
  baseline_end_cents: number;
  lowest: { date: string; balance_cents: number } | null;
  totals: { income_cents: number; fixe_cents: number; essentiel_cents: number; plaisir_cents: number; epargne_cents: number };
  income_cents: number;
  fixed_out_cents: number;
  variable_total_cents: number;
  daily_variable_cents: number;
  events: ForecastEventOut[];
  /** Prévu d'ici l'horizon pour chaque catégorie sans date fixe (avec le scénario, et sans). */
  categories: ForecastCategory[];
  points: {
    date: string;
    socle_cents: number;
    after_essentials_cents: number;
    balance_cents: number;
    baseline_cents: number;
    income_cum: number;
    fixed_cum: number;
    essentiel_cum: number;
    plaisir_cum: number;
    transfer_cum: number;
  }[];
  model: ModelView;
  scenario: ScenarioIn & { active: boolean };
}

export interface ProjectionMonth {
  month: string;
  partial: boolean;
  income_cents: number;
  fixe_cents: number;
  essentiel_cents: number;
  plaisir_cents: number;
  epargne_cents: number;
  net_cents: number;
  end_balance_cents: number;
  baseline_end_cents: number;
}

export interface Projection {
  today: string;
  account_ids: number[];
  accounts: string[];
  start_balance_cents: number;
  end_balance_cents: number;
  baseline_end_cents: number;
  avg_net_cents: number;
  avg_saving_cents: number;
  lowest: { month: string; balance_cents: number } | null;
  first_negative_month: string | null;
  months: ProjectionMonth[];
  model: ModelView;
  scenario: ScenarioIn & { active: boolean };
}
