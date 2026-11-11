import type { AccountType } from "./api";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export const formatCents = (cents: number) => eur.format(cents / 100);

export const formatDate = (iso: string) => new Date(iso).toLocaleDateString("fr-FR");

/** "1 234,56" ou "-12.5" → centimes. Renvoie null si la saisie est invalide. */
export function parseEuros(input: string): number | null {
  const clean = input.replace(/\s|€/g, "").replace(",", ".");
  if (clean === "" || !/^-?\d+(\.\d{0,2})?$/.test(clean)) return null;
  return Math.round(parseFloat(clean) * 100);
}

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  courant: "Compte courant",
  epargne: "Épargne",
  investissement: "Investissement",
  paypal: "PayPal",
  especes: "Espèces",
  credit: "Crédit",
  bien: "Bien (immobilier, véhicule…)",
};

/** Date locale au format AAAA-MM-JJ (sans décalage de fuseau). */
export function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export type PeriodKey = "month" | "last_month" | "3m" | "year" | "12m" | "all" | "custom";

export const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: "month", label: "Ce mois-ci" },
  { key: "last_month", label: "Mois dernier" },
  { key: "3m", label: "3 derniers mois" },
  { key: "year", label: "Cette année" },
  { key: "12m", label: "12 derniers mois" },
  { key: "all", label: "Depuis le début" },
  { key: "custom", label: "Personnalisée…" },
];

/** Bornes [début, fin] d'une période prédéfinie (null = pas de borne). */
export function periodRange(key: PeriodKey, today = new Date()): [string | null, string | null] {
  const y = today.getFullYear();
  const m = today.getMonth();
  switch (key) {
    case "month":
      return [isoDate(new Date(y, m, 1)), isoDate(today)];
    case "last_month":
      return [isoDate(new Date(y, m - 1, 1)), isoDate(new Date(y, m, 0))];
    case "3m":
      return [isoDate(new Date(y, m - 2, 1)), isoDate(today)];
    case "year":
      return [isoDate(new Date(y, 0, 1)), isoDate(today)];
    case "12m":
      return [isoDate(new Date(y - 1, m, today.getDate() + 1)), isoDate(today)];
    default:
      return [null, null];
  }
}
