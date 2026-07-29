"use client";

import { useEffect, useState } from "react";
import { saveFoodEstimateItems, type SavedFoodItem } from "./actions";
import type {
  FoodEstimateItem,
  FoodEstimateResponse,
} from "@/app/api/food/estimate/route";
import { Card } from "@/components/ui/Card";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";

const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"];

function resizeToBase64(file: File, maxDim = 1024): Promise<string> {
  return new Promise((resolve, reject) => {
    createImageBitmap(file)
      .then((img) => {
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          if (width > height) {
            height = Math.round((height * maxDim) / width);
            width = maxDim;
          } else {
            width = Math.round((width * maxDim) / height);
            height = maxDim;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Canvas not supported"));
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              reject(new Error("Failed to encode image"));
              return;
            }
            const reader = new FileReader();
            reader.onloadend = () => {
              const dataUrl = reader.result as string;
              resolve(dataUrl.split(",")[1]);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          },
          "image/jpeg",
          0.85,
        );
      })
      .catch(reject);
  });
}

export function PhotoFoodLogger() {
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [base64, setBase64] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [items, setItems] = useState<FoodEstimateItem[]>([]);
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [mealType, setMealType] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [edited, setEdited] = useState<Set<number>>(new Set());
  const [isDragging, setIsDragging] = useState(false);

  async function handleFile(file: File) {
    if (!file.type.startsWith("image/")) {
      setAnalyzeError("That doesn't look like an image file.");
      return;
    }

    setAnalyzeError(null);
    setItems([]);
    setEdited(new Set());
    setImagePreview(URL.createObjectURL(file));

    const encoded = await resizeToBase64(file);
    setBase64(encoded);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  }

  function clearPhoto() {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(null);
    setBase64(null);
    setItems([]);
    setAssumptions([]);
    setEdited(new Set());
    setAnalyzeError(null);
  }

  function handleDrop(e: React.DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  // Paste an image from the clipboard (e.g. cmd+V a screenshot) anywhere on
  // the page while this component is mounted.
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) =>
        i.type.startsWith("image/"),
      );
      const file = item?.getAsFile();
      if (file) void handleFile(file);
    }
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, []);

  async function handleAnalyze() {
    if (!base64) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await fetch("/api/food/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageBase64: base64, mediaType: "image/jpeg" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Estimate failed");
      const estimate = data as FoodEstimateResponse;
      setItems(estimate.items);
      setAssumptions(estimate.assumptions);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Estimate failed");
    } finally {
      setAnalyzing(false);
    }
  }

  function updateItem(
    index: number,
    field:
      | "name"
      | "serving_description"
      | "calories"
      | "protein_g"
      | "carbs_g"
      | "fat_g"
      | "fiber_g",
    value: string,
  ) {
    setItems((prev) =>
      prev.map((item, i) => {
        if (i !== index) return item;
        const isNumeric = field !== "name" && field !== "serving_description";
        return {
          ...item,
          [field]: isNumeric ? Number(value) : value,
        };
      }),
    );
    setEdited((prev) => new Set(prev).add(index));
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
    setEdited((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i < index) next.add(i);
        if (i > index) next.add(i - 1);
      });
      return next;
    });
  }

  async function handleSave() {
    setSaveError(null);
    setSaving(true);
    try {
      const payload: SavedFoodItem[] = items.map((item, i) => ({
        ...item,
        editedByUser: edited.has(i),
      }));
      await saveFoodEstimateItems({ items: payload, mealType });
    } catch (err) {
      setSaving(false);
      setSaveError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-2xl border-2 border-dashed px-3 py-6 text-center text-sm transition-colors ${
          isDragging ? "border-teal bg-teal-pale" : "border-line text-ink-soft"
        }`}
      >
        <span>
          Drag and drop a photo, paste from clipboard, or click to choose one
        </span>
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileChange}
          className="hidden"
        />
      </label>

      {imagePreview && (
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imagePreview}
            alt="Food to analyze"
            className="max-h-64 w-full rounded-2xl object-cover"
          />
          <button
            type="button"
            onClick={clearPhoto}
            aria-label="Remove photo"
            className="absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded-full bg-ink/70 text-white"
          >
            ×
          </button>
        </div>
      )}

      {imagePreview && items.length === 0 && (
        <button
          type="button"
          onClick={handleAnalyze}
          disabled={analyzing || !base64}
          className="rounded-full bg-teal px-4 py-2.5 font-medium text-white disabled:opacity-50"
        >
          {analyzing ? "Analyzing…" : "Analyze photo"}
        </button>
      )}

      {analyzeError && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {analyzeError}
        </p>
      )}

      {items.length > 0 && (
        <>
          {assumptions.length > 0 && (
            <ul className="rounded-xl bg-gold-pale px-3 py-2 text-sm text-amber">
              {assumptions.map((a, i) => (
                <li key={i}>• {a}</li>
              ))}
            </ul>
          )}

          {saveError && (
            <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
              {saveError}
            </p>
          )}

          {items.map((item, i) => (
            <Card key={i} className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between gap-2">
                <input
                  value={item.name}
                  onChange={(e) => updateItem(i, "name", e.target.value)}
                  className="flex-1 rounded-lg border border-line px-2 py-1 font-semibold"
                />
                <button
                  type="button"
                  onClick={() => removeItem(i)}
                  className="font-mono text-xs text-red uppercase"
                >
                  Remove
                </button>
              </div>

              <div className="flex items-center gap-2">
                <input
                  value={item.serving_description}
                  onChange={(e) =>
                    updateItem(i, "serving_description", e.target.value)
                  }
                  className="flex-1 rounded-lg border border-line px-2 py-1 font-mono text-xs text-ink-soft"
                />
                <ConfidenceBadge level={item.confidence.serving_description} hideHigh />
              </div>

              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
                <label className="flex flex-col gap-1 text-xs">
                  <span className="flex items-center gap-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                    Calories <ConfidenceBadge level={item.confidence.calories} hideHigh />
                  </span>
                  <input
                    type="number"
                    value={item.calories}
                    onChange={(e) => updateItem(i, "calories", e.target.value)}
                    className="rounded-lg border border-line px-2 py-1"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="flex items-center gap-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                    Protein (g) <ConfidenceBadge level={item.confidence.protein_g} hideHigh />
                  </span>
                  <input
                    type="number"
                    value={item.protein_g}
                    onChange={(e) => updateItem(i, "protein_g", e.target.value)}
                    className="rounded-lg border border-line px-2 py-1"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="flex items-center gap-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                    Carbs (g) <ConfidenceBadge level={item.confidence.carbs_g} hideHigh />
                  </span>
                  <input
                    type="number"
                    value={item.carbs_g}
                    onChange={(e) => updateItem(i, "carbs_g", e.target.value)}
                    className="rounded-lg border border-line px-2 py-1"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="flex items-center gap-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                    Fat (g) <ConfidenceBadge level={item.confidence.fat_g} hideHigh />
                  </span>
                  <input
                    type="number"
                    value={item.fat_g}
                    onChange={(e) => updateItem(i, "fat_g", e.target.value)}
                    className="rounded-lg border border-line px-2 py-1"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  <span className="flex items-center gap-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                    Fiber (g) <ConfidenceBadge level={item.confidence.fiber_g} hideHigh />
                  </span>
                  <input
                    type="number"
                    value={item.fiber_g}
                    onChange={(e) => updateItem(i, "fiber_g", e.target.value)}
                    className="rounded-lg border border-line px-2 py-1"
                  />
                </label>
              </div>
            </Card>
          ))}

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

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || items.length === 0}
            className="rounded-full bg-teal px-4 py-2.5 font-medium text-white disabled:opacity-50"
          >
            {saving ? "Saving…" : `Save ${items.length} item${items.length === 1 ? "" : "s"}`}
          </button>
        </>
      )}
    </div>
  );
}
