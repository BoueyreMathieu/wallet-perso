import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Tag, TagRef, api } from "../api";

interface Ctx {
  tags: Tag[];
  byId: Map<number, Tag>;
  reload: () => Promise<void>;
  create: (name: string) => Promise<Tag>;
}

const TagsContext = createContext<Ctx>({
  tags: [],
  byId: new Map(),
  reload: async () => {},
  create: async () => {
    throw new Error("TagsProvider manquant");
  },
});

const PALETTE = ["#0f766e", "#7c3aed", "#db2777", "#ea580c", "#2563eb", "#16a34a", "#a16207", "#475569"];

export function TagsProvider({ children }: { children: ReactNode }) {
  const [tags, setTags] = useState<Tag[]>([]);
  const reload = useCallback(() => api.get<Tag[]>("/tags").then(setTags), []);
  useEffect(() => {
    reload();
  }, [reload]);
  const value = useMemo<Ctx>(
    () => ({
      tags,
      byId: new Map<number, Tag>(tags.map((t) => [t.id, t] as [number, Tag])),
      reload,
      create: async (name: string) => {
        const tag = await api.post<Tag>("/tags", { name, color: PALETTE[tags.length % PALETTE.length] });
        await reload();
        return tag;
      },
    }),
    [tags, reload],
  );
  return <TagsContext.Provider value={value}>{children}</TagsContext.Provider>;
}

export const useTags = () => useContext(TagsContext);

const SOURCE_HINT: Record<TagRef["source"], string> = {
  manuel: "posée à la main",
  vendeur: "héritée du vendeur",
  service: "héritée du service",
};

export function TagChip({ name, color, source }: { name: string; color: string | null; source?: TagRef["source"] }) {
  return (
    <span
      title={source ? SOURCE_HINT[source] : undefined}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${source && source !== "manuel" ? "border border-dashed" : ""}`}
      style={{ background: `${color ?? "#94a3b8"}22`, color: color ?? "#475569", borderColor: color ?? "#94a3b8" }}
    >
      #{name}
    </span>
  );
}

/** Sélection de plusieurs étiquettes, avec création à la volée. */
export function TagPicker({ value, onChange }: { value: number[]; onChange: (ids: number[]) => void }) {
  const { tags, create } = useTags();
  const [name, setName] = useState("");
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  const add = async () => {
    const n = name.trim();
    if (!n) return;
    const existing = tags.find((t) => t.name.toLowerCase() === n.toLowerCase());
    const tag = existing ?? (await create(n));
    if (!value.includes(tag.id)) onChange([...value, tag.id]);
    setName("");
  };
  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => toggle(t.id)}
          className={`rounded-full border px-2 py-0.5 text-xs ${value.includes(t.id) ? "" : "opacity-50"}`}
          style={{ borderColor: t.color ?? "#94a3b8", color: t.color ?? undefined, background: value.includes(t.id) ? `${t.color ?? "#94a3b8"}22` : undefined }}
        >
          {value.includes(t.id) ? "✓ " : ""}#{t.name}
        </button>
      ))}
      <input
        className="w-32 rounded-full border border-slate-300 bg-transparent px-2 py-0.5 text-xs dark:border-slate-700"
        placeholder="+ nouvelle étiquette"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
    </div>
  );
}

/** Liste déroulante d'une seule étiquette (filtres, actions groupées). */
export function TagSelect({
  value,
  onChange,
  emptyLabel = "Toutes les étiquettes",
  className = "input",
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  emptyLabel?: string;
  className?: string;
}) {
  const { tags } = useTags();
  return (
    <select className={className} value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{emptyLabel}</option>
      {tags.map((t) => (
        <option key={t.id} value={t.id}>#{t.name}</option>
      ))}
    </select>
  );
}
