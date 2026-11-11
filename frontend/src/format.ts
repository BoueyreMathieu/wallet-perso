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
