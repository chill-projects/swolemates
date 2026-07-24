"use client";

import { useState } from "react";
import { logFood } from "./actions";
import type { FoodProduct } from "@/lib/openfoodfacts";
import { Card } from "@/components/ui/Card";

const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"];

function scaled(per100g: number | null, grams: number) {
  return per100g === null ? 0 : Math.round((per100g * grams) / 100);
}

export function FoodSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodProduct[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [selected, setSelected] = useState<FoodProduct | null>(null);
  const [grams, setGrams] = useState("100");
  const [mealType, setMealType] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSearch() {
    if (query.trim().length < 2) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await fetch(`/api/food/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Search failed");
      setResults(data.products);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function handleLog() {
    if (!selected) return;
    setSaveError(null);

    const gramsNum = Number(grams);
    if (!gramsNum || gramsNum <= 0) {
      setSaveError("Enter a valid amount in grams.");
      return;
    }

    setSaving(true);
    try {
      await logFood({
        name: selected.name,
        servingDescription: `${gramsNum}g`,
        calories: scaled(selected.caloriesPer100g, gramsNum),
        proteinG: scaled(selected.proteinPer100g, gramsNum),
        carbsG: scaled(selected.carbsPer100g, gramsNum),
        fatG: scaled(selected.fatPer100g, gramsNum),
        fiberG:
          selected.fiberPer100g === null
            ? null
            : scaled(selected.fiberPer100g, gramsNum),
        mealType,
        barcode: selected.barcode,
      });
    } catch (err) {
      setSaving(false);
      setSaveError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  if (selected) {
    const gramsNum = Number(grams) || 0;
    return (
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => setSelected(null)}
          className="self-start font-mono text-xs tracking-wide text-ink-soft uppercase"
        >
          ← Back to results
        </button>

        <h2 className="font-display text-lg font-semibold">{selected.name}</h2>
        {selected.brand && (
          <p className="font-mono text-xs text-ink-soft">{selected.brand}</p>
        )}

        {saveError && (
          <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
            {saveError}
          </p>
        )}

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Amount (grams)
          </span>
          <input
            type="number"
            inputMode="numeric"
            value={grams}
            onChange={(e) => setGrams(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Meal (optional)
          </span>
          <select
            value={mealType}
            onChange={(e) => setMealType(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          >
            <option value="">—</option>
            {MEAL_TYPES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>

        <div className="rounded-2xl bg-teal px-5 py-4 text-white">
          <div className="font-display text-2xl font-semibold">
            {scaled(selected.caloriesPer100g, gramsNum)}
            <span className="ml-1 font-mono text-xs font-normal opacity-80">cal</span>
          </div>
          <div className="mt-1 flex gap-3 font-mono text-xs opacity-90">
            <span>P {scaled(selected.proteinPer100g, gramsNum)}g</span>
            <span>C {scaled(selected.carbsPer100g, gramsNum)}g</span>
            <span>F {scaled(selected.fatPer100g, gramsNum)}g</span>
            {selected.fiberPer100g !== null && (
              <span>Fiber {scaled(selected.fiberPer100g, gramsNum)}g</span>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={handleLog}
          disabled={saving}
          className="rounded-full bg-teal px-4 py-2.5 font-medium text-white disabled:opacity-50"
        >
          {saving ? "Logging…" : "Log this"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="Search packaged food, e.g. 'chobani greek yogurt'"
          className="flex-1 rounded-xl border border-line bg-card px-3 py-2"
        />
        <button
          type="button"
          onClick={handleSearch}
          disabled={searching}
          className="rounded-full bg-teal px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {searching ? "…" : "Search"}
        </button>
      </div>

      {searchError && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {searchError}
        </p>
      )}

      {results.length === 0 && !searching && (
        <p className="text-sm text-ink-soft">
          No results yet — try a search above. Coverage is best for major
          packaged/branded products.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {results.map((product) => (
          <li key={product.barcode}>
            <button type="button" onClick={() => setSelected(product)} className="w-full text-left">
              <Card className="hover:border-teal">
                <div className="font-semibold">{product.name}</div>
                <div className="mt-0.5 font-mono text-xs text-ink-soft">
                  {product.brand ? `${product.brand} · ` : ""}
                  {product.caloriesPer100g} kcal / 100g
                </div>
              </Card>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
