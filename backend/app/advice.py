"""Conseils d'optimisation (cœur sans base de données, testable seul).

Chaque règle lit un `Context` (tendances par catégorie, récurrents, soldes, revenus…) et renvoie des conseils :
titre, détail, gain mensuel estimé et une action (simuler dans Trésorerie, ou ouvrir une page). Le service
(`app/services/advice.py`) construit le contexte depuis la base et retire les conseils écartés par l'utilisateur.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

SUBSCRIPTION_CATEGORIES = {"Streaming", "Musique", "Jeux en ligne", "Logiciels / cloud", "Presse", "Salle de sport"}
DELIVERY_CATEGORIES = {"Livraison", "Fast-food"}
FEES_CATEGORIES = {"Frais bancaires"}
SAVINGS_EXAMPLE_RATE = 0.015  # taux d'exemple pour l'argent qui dort (à adapter : les taux des livrets changent)


@dataclass
class CatTrend:
    category_id: int | None
    name: str
    layer: str  # fixe / essentiel / plaisir
    monthly: int  # niveau habituel (centimes)
    history: list[int]  # mois complets, du plus ancien au plus récent


@dataclass
class Series:
    id: int
    label: str
    category: str | None
    amount: int  # signé
    monthly: int  # équivalent mensuel (positif = coût)
    is_transfer: bool
    status: str
    previous_amount: int | None = None
    price_changed_on: date | None = None
    maybe_ended: bool = False


@dataclass
class SmallSpender:
    """Vendeur de petits achats fréquents sur les 30 derniers jours."""

    merchant: str
    category_id: int | None
    count: int
    total: int


@dataclass
class Context:
    today: date
    trends: list[CatTrend] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    small: list[SmallSpender] = field(default_factory=list)
    liquid_balance: int = 0  # comptes courants + PayPal
    has_savings_account: bool = False
    monthly_spending: int = 0  # dépenses habituelles d'un mois (toutes couches)
    income_months: list[int] = field(default_factory=list)  # revenus des derniers mois complets
    spending_months: list[int] = field(default_factory=list)  # dépenses des mêmes mois (hors virements)
    fees_3_months: int = 0
    lowest_30_days: int | None = None  # point bas prévu sur 30 jours
    lowest_date: date | None = None
    uncategorized: int = 0
    to_confirm: int = 0
    consent_days_left: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Advice:
    id: str
    kind: str  # depense / abonnement / epargne / risque / menage
    severity: str  # alerte / conseil / info
    icon: str
    title: str
    detail: str
    gain_monthly_cents: int = 0
    action: dict | None = None  # {"type": "scenario", "scenario": {...}} ou {"type": "link", "to": "/…"}

    def to_dict(self) -> dict:
        return asdict(self)


def euros(cents: int) -> str:
    v = abs(cents) / 100
    s = f"{v:,.0f}" if v >= 100 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",") + " €"


def _avg(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _scenario(**kw) -> dict:
    return {"type": "scenario", "label": "Simuler", "scenario": kw}


def _link(to: str, label: str) -> dict:
    return {"type": "link", "to": to, "label": label}


# --- Règles -----------------------------------------------------------------------------------------


def drifting_categories(ctx: Context) -> list[Advice]:
    """Poste en dérive : les 3 derniers mois dépassent les 3 précédents d'au moins 15 % et 20 €/mois."""
    out = []
    for t in ctx.trends:
        if t.layer == "fixe" or len(t.history) < 6 or t.category_id is None:
            continue
        recent, before = _avg(t.history[-3:]), _avg(t.history[-6:-3])
        diff = recent - before
        if before > 0 and diff >= 2000 and recent >= before * 1.15:
            out.append(Advice(
                f"derive:{t.category_id}", "depense", "conseil", "📈", f"{t.name} en hausse",
                f"{euros(round(recent))} par mois ces 3 derniers mois, contre {euros(round(before))} avant (+{round(diff / before * 100)} %).",
                round(diff), _scenario(targets={str(t.category_id): round(before)}),
            ))
    return out


def rising_pleasures(ctx: Context) -> list[Advice]:
    """Plaisirs en hausse dans l'ensemble (+15 %, au moins 30 €/mois)."""
    hist = [t.history for t in ctx.trends if t.layer == "plaisir" and len(t.history) >= 6]
    if not hist:
        return []
    recent = sum(_avg(h[-3:]) for h in hist)
    before = sum(_avg(h[-6:-3]) for h in hist)
    diff = recent - before
    if before <= 0 or diff < 3000 or recent < before * 1.15:
        return []
    pct = max(10, min(90, round(before / recent * 100 / 10) * 10))
    return [Advice(
        "plaisirs:hausse", "depense", "conseil", "🎉", "Tes plaisirs augmentent",
        f"{euros(round(recent))} par mois ces 3 derniers mois, contre {euros(round(before))} avant. Revenir au niveau d'avant libère {euros(round(diff))} par mois.",
        round(diff), _scenario(plaisir_pct=pct),
    )]


def price_increases(ctx: Context) -> list[Advice]:
    """Abonnement ou prélèvement dont le prix a augmenté ces 4 derniers mois."""
    out = []
    for s in ctx.series:
        if s.amount >= 0 or s.previous_amount is None or s.price_changed_on is None or s.status not in ("actif", "suggere"):
            continue
        if (ctx.today - s.price_changed_on).days > 120 or abs(s.amount) <= abs(s.previous_amount):
            continue
        inc = abs(s.amount) - abs(s.previous_amount)
        out.append(Advice(
            f"hausse_prix:{s.id}", "abonnement", "conseil", "🏷️", f"{s.label} a augmenté",
            f"{euros(s.previous_amount)} → {euros(s.amount)} depuis le {s.price_changed_on.strftime('%d/%m')}. "
            "Une offre moins chère, ou à résilier si tu t'en sers peu ?",
            round(inc * s.monthly / max(abs(s.amount), 1)), _link("/prevoir/recurrents", "Voir mes récurrents"),
        ))
    return out


def duplicate_subscriptions(ctx: Context) -> list[Advice]:
    """Plusieurs abonnements actifs dans la même catégorie (deux plateformes vidéo, deux stockages en ligne…)."""
    by_cat: dict[str, list[Series]] = {}
    for s in ctx.series:
        if s.amount < 0 and not s.is_transfer and s.status in ("actif", "suggere") and s.category in SUBSCRIPTION_CATEGORIES:
            by_cat.setdefault(s.category, []).append(s)
    out = []
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda s: s.monthly)
        names = ", ".join(s.label for s in items)
        out.append(Advice(
            f"doublon:{cat}", "abonnement", "conseil", "👯", f"{len(items)} abonnements « {cat} »",
            f"{names} : {euros(sum(s.monthly for s in items))} par mois. En garder un seul ?",
            items[0].monthly, _link("/prevoir/recurrents", "Voir mes abonnements"),
        ))
    return out


def maybe_ended(ctx: Context) -> list[Advice]:
    """Récurrent pas vu depuis longtemps mais toujours compté dans les prévisions."""
    out = []
    for s in ctx.series:
        if s.maybe_ended and s.status == "actif" and s.amount < 0:
            out.append(Advice(
                f"fini:{s.id}", "abonnement", "info", "❓", f"{s.label} : résilié ?",
                "Plus vu depuis un moment mais toujours compté dans tes prévisions. Marque-le « terminé » s'il est fini.",
                0, _link("/prevoir/recurrents", "Vérifier"),
            ))
    return out


def small_purchases(ctx: Context) -> list[Advice]:
    """Petits achats qui s'accumulent : au moins 10 passages de moins de 15 € en 30 jours, 40 € au total."""
    out = []
    for m in ctx.small:
        if m.count >= 10 and m.total >= 4000:
            gain = round(m.total * 0.3)
            out.append(Advice(
                f"petits:{m.merchant}", "depense", "info", "🥐", f"{m.count} passages chez {m.merchant}",
                f"{euros(m.total)} en 30 jours, par petites sommes. Un passage sur trois en moins : {euros(gain)} par mois.",
                gain, _link("/vendeurs", "Voir mes vendeurs"),
            ))
    return out


def delivery(ctx: Context) -> list[Advice]:
    """Livraison / fast-food : au moins 60 €/mois."""
    items = [t for t in ctx.trends if t.name in DELIVERY_CATEGORIES and t.category_id is not None]
    total = sum(t.monthly for t in items)
    if total < 6000:
        return []
    gain = round(total * 0.5 * 0.6)  # la moitié cuisinée maison coûte environ 40 % du prix livré
    return [Advice(
        "livraison", "depense", "conseil", "🛵", "La livraison te coûte cher",
        f"{euros(total)} par mois en livraison et fast-food. En cuisiner la moitié : environ {euros(gain)} de gagnés par mois.",
        gain, _scenario(targets={str(t.category_id): round(t.monthly / 2) for t in items}),
    )]


def idle_cash(ctx: Context) -> list[Advice]:
    """Argent qui dort sur les comptes courants au-delà d'un matelas d'un mois et demi de dépenses."""
    cushion = round(ctx.monthly_spending * 1.5)
    idle = ctx.liquid_balance - cushion
    if ctx.monthly_spending <= 0 or idle < 100000:
        return []
    gain = round(idle * SAVINGS_EXAMPLE_RATE / 12)
    where = "ton livret" if ctx.has_savings_account else "un livret"
    return [Advice(
        "argent_qui_dort", "epargne", "conseil", "💤", f"{euros(idle)} dorment sur tes comptes courants",
        f"Au-delà d'un matelas de {euros(cushion)} (un mois et demi de dépenses). Placés sur {where}, à "
        f"{f'{SAVINGS_EXAMPLE_RATE * 100:.1f}'.replace('.', ',')} % par exemple : environ {euros(gain * 12)} par an.",
        gain, _link("/comptes", "Voir mes comptes"),
    )]


def bank_fees(ctx: Context) -> list[Advice]:
    if ctx.fees_3_months < 300:
        return []
    monthly = round(ctx.fees_3_months / 3)
    return [Advice(
        "frais", "depense", "conseil", "🏦", "Frais bancaires",
        f"{euros(ctx.fees_3_months)} en 3 mois. Carte, tenue de compte, agios : une banque en ligne ou une offre moins chère ?",
        monthly, _link("/operations", "Voir les opérations"),
    )]


def overdraft_risk(ctx: Context) -> list[Advice]:
    if ctx.lowest_30_days is None or ctx.lowest_30_days >= 0:
        return []
    when = f" le {ctx.lowest_date.strftime('%d/%m')}" if ctx.lowest_date else ""
    return [Advice(
        "decouvert", "risque", "alerte", "⚠️", "Découvert possible ce mois-ci",
        f"Ton solde pourrait descendre à {euros(ctx.lowest_30_days)}{when}. Approvisionne le compte avant, ou décale une dépense.",
        0, _link("/prevoir/tresorerie", "Voir la trésorerie"),
    )]


def savings_rate(ctx: Context) -> list[Advice]:
    """Taux d'épargne des 3 derniers mois sous 10 % : proposer d'épargner 10 % des revenus."""
    inc, spent = ctx.income_months[-3:], ctx.spending_months[-3:]
    if len(inc) < 3 or sum(inc) <= 0:
        return []
    rate = (sum(inc) - sum(spent)) / sum(inc)
    if rate >= 0.10:
        return []
    target = round(_avg(inc) * 0.10)
    return [Advice(
        "taux_epargne", "epargne", "conseil", "🐷", f"Taux d'épargne : {round(rate * 100)} %",
        f"Ces 3 derniers mois, il te reste {round(rate * 100)} % de tes revenus. Viser 10 %, c'est mettre {euros(target)} de côté chaque mois.",
        0, _scenario(extra_saving_cents=target),
    )]


def housekeeping(ctx: Context) -> list[Advice]:
    out = []
    for label, days in ctx.consent_days_left:
        if days <= 14:
            out.append(Advice(
                f"consentement:{label}", "menage", "alerte" if days <= 3 else "info", "🔑", f"Autorisation {label} bientôt expirée",
                f"Plus que {max(days, 0)} jour(s) : renouvelle-la pour que la synchro continue.", 0, _link("/parametres/connexions", "Renouveler"),
            ))
    if ctx.uncategorized >= 10:
        out.append(Advice("a_categoriser", "menage", "info", "🏷️", f"{ctx.uncategorized} opérations à catégoriser",
                          "Les prévisions et les conseils sont plus justes quand tout est catégorisé.", 0, _link("/operations?a_categoriser=1", "Catégoriser")))
    if ctx.to_confirm >= 1:
        out.append(Advice("a_confirmer", "menage", "info", "✨", f"{ctx.to_confirm} récurrent(s) à confirmer",
                          "Ils comptent déjà dans tes prévisions : confirme-les ou écarte ceux qui n'en sont pas.", 0, _link("/prevoir/recurrents", "Confirmer")))
    return out


RULES = (overdraft_risk, price_increases, duplicate_subscriptions, drifting_categories, rising_pleasures, delivery, small_purchases,
         idle_cash, bank_fees, savings_rate, maybe_ended, housekeeping)
SEVERITY_ORDER = {"alerte": 0, "conseil": 1, "info": 2}


def advise(ctx: Context) -> list[Advice]:
    """Tous les conseils : alertes d'abord, puis par gain mensuel décroissant."""
    items = [a for rule in RULES for a in rule(ctx)]
    return sorted(items, key=lambda a: (SEVERITY_ORDER.get(a.severity, 3), -a.gain_monthly_cents))
