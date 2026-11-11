import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { Category, api } from "../api";

interface Ctx {
  categories: Category[];
  byId: Map<number, Category>;
  /** « Alimentation › Courses » */
  pathOf: (id: number | null) => string;
}

const CategoriesContext = createContext<Ctx>({ categories: [], byId: new Map(), pathOf: () => "" });

export function CategoriesProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<Category[]>([]);
  useEffect(() => {
    api.get<Category[]>("/categories").then(setCategories);
  }, []);
  const value = useMemo(() => {
    const byId = new Map<number, Category>(categories.map((c) => [c.id, c] as [number, Category]));
    const pathOf = (id: number | null) => {
      if (id === null) return "";
      const c = byId.get(id);
      if (!c) return "";
      const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
      return parent ? `${parent.name} › ${c.name}` : c.name;
    };
    return { categories, byId, pathOf };
  }, [categories]);
  return <CategoriesContext.Provider value={value}>{children}</CategoriesContext.Provider>;
}

export const useCategories = () => useContext(CategoriesContext);

export function CategorySelect({
  value,
  onChange,
  emptyLabel = "— Non catégorisé —",
  className = "input",
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  emptyLabel?: string;
  className?: string;
}) {
  const { categories } = useCategories();
  const parents = categories.filter((c) => c.parent_id === null);
  return (
    <select
      className={className}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    >
      <option value="">{emptyLabel}</option>
      {parents.map((p) => (
        <optgroup key={p.id} label={p.name}>
          <option value={p.id}>{p.name} (général)</option>
          {categories
            .filter((c) => c.parent_id === p.id)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  );
}

export function CategoryBadge({ id }: { id: number | null }) {
  const { byId, pathOf } = useCategories();
  const c = id !== null ? byId.get(id) : undefined;
  if (!c) return <span className="text-xs text-amber-600">À catégoriser</span>;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-slate-500">
      <span className="h-2 w-2 rounded-full" style={{ background: c.color ?? "#999" }} />
      {pathOf(id)}
    </span>
  );
}
