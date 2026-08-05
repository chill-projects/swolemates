import { useState } from "react";

/**
 * PROTOTYPE — throwaway. Answers: when a food has no barcode/search match, what does
 * typing it in from scratch look like? Full form vs progressive disclosure vs
 * preset-driven field selection. See ticket #4 (Nutrition v1) on the map (#1).
 *
 * Three variants, switchable via ?variant=, mounted at /prototype/manual-entry (see
 * App.tsx). No persistence — state resets on reload. Not part of the real app; delete
 * this file and its App.tsx hook once the answer is captured on the throwaway branch
 * per the /prototype skill.
 */

type FieldKey = "calories" | "protein_g" | "carbs_g" | "fat_g" | "fiber_g";

const FIELDS: { key: FieldKey; label: string }[] = [
  { key: "calories", label: "Calories" },
  { key: "protein_g", label: "Protein (g)" },
  { key: "carbs_g", label: "Carbs (g)" },
  { key: "fat_g", label: "Fat (g)" },
  { key: "fiber_g", label: "Fiber (g)" },
];

// What actually gets written: one log_values row per field the user filled in.
// Empty/untouched fields never become rows — a calories-only entry is 1 row, not 5.
function toLogValues(name: string, values: Partial<Record<FieldKey, string>>) {
  return {
    name,
    source: "manual" as const,
    values: Object.entries(values)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([trackable_key, value]) => ({ trackable_key, value: Number(value) })),
  };
}

function StatePanel({ label, data }: { label: string; data: unknown }) {
  return (
    <details style={{ marginTop: "1.5rem", fontSize: "0.75rem" }}>
      <summary className="muted">{label} (debug state)</summary>
      <pre
        style={{
          background: "rgba(127,127,127,0.1)",
          padding: "0.75rem",
          borderRadius: "0.375rem",
          overflowX: "auto",
        }}
      >
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Variant A — full form up front. Every field visible immediately, matching the
// existing photo-review / template-item card exactly. One component reused as-is.
// ---------------------------------------------------------------------------

function VariantA() {
  const [name, setName] = useState("");
  const [values, setValues] = useState<Partial<Record<FieldKey, string>>>({});
  const [logged, setLogged] = useState<ReturnType<typeof toLogValues>[]>([]);

  function save() {
    if (!name) return;
    setLogged((prev) => [toLogValues(name, values), ...prev]);
    setName("");
    setValues({});
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>A — Full form up front</h2>
      <p className="muted">
        Every field visible from the start — the exact same card used for photo-estimate review and template
        editing. Leave macros blank if you don&apos;t know them.
      </p>

      <div style={{ border: "1px solid currentColor", borderRadius: "0.5rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <input placeholder="Food name" value={name} onChange={(e) => setName(e.target.value)} style={{ fontWeight: 600 }} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.4rem" }}>
          {FIELDS.map((f) => (
            <label key={f.key} style={{ fontSize: "0.65rem", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
              {f.label}
              <input
                type="number"
                placeholder="—"
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
              />
            </label>
          ))}
        </div>
        <button type="button" onClick={save} disabled={!name}>
          Log it
        </button>
      </div>

      <strong>Logged</strong>
      {logged.map((l, i) => (
        <div key={i} className="muted">
          {l.name}: {l.values.map((v) => `${v.trackable_key}=${v.value}`).join(", ") || "(no values)"}
        </div>
      ))}

      <StatePanel label="Variant A state" data={{ name, values, logged }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant B — progressive disclosure. Start with name + calories only; macros
// reveal on demand. Same end state (log_values rows) via a smaller first ask.
// ---------------------------------------------------------------------------

function VariantB() {
  const [name, setName] = useState("");
  const [values, setValues] = useState<Partial<Record<FieldKey, string>>>({});
  const [expanded, setExpanded] = useState(false);
  const [logged, setLogged] = useState<ReturnType<typeof toLogValues>[]>([]);

  function save() {
    if (!name) return;
    setLogged((prev) => [toLogValues(name, values), ...prev]);
    setName("");
    setValues({});
    setExpanded(false);
  }

  const macroFields = FIELDS.filter((f) => f.key !== "calories");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>B — Progressive disclosure</h2>
      <p className="muted">
        Just name + calories to start — the two things you almost always know. Macros are a tap away, not
        upfront.
      </p>

      <div style={{ border: "1px solid currentColor", borderRadius: "0.5rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <input placeholder="Food name" value={name} onChange={(e) => setName(e.target.value)} style={{ fontWeight: 600 }} />
        <label style={{ fontSize: "0.65rem", display: "flex", flexDirection: "column", gap: "0.15rem", maxWidth: "8rem" }}>
          Calories
          <input
            type="number"
            placeholder="—"
            value={values.calories ?? ""}
            onChange={(e) => setValues((prev) => ({ ...prev, calories: e.target.value }))}
          />
        </label>

        {!expanded && (
          <button type="button" onClick={() => setExpanded(true)} style={{ alignSelf: "flex-start", fontSize: "0.8rem" }}>
            + Add macros
          </button>
        )}

        {expanded && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem" }}>
            {macroFields.map((f) => (
              <label key={f.key} style={{ fontSize: "0.65rem", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                {f.label}
                <input
                  type="number"
                  placeholder="—"
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
              </label>
            ))}
          </div>
        )}

        <button type="button" onClick={save} disabled={!name}>
          Log it
        </button>
      </div>

      <strong>Logged</strong>
      {logged.map((l, i) => (
        <div key={i} className="muted">
          {l.name}: {l.values.map((v) => `${v.trackable_key}=${v.value}`).join(", ") || "(no values)"}
        </div>
      ))}

      <StatePanel label="Variant B state" data={{ name, values, expanded, logged }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant C — preset chips choose the field set. Structurally different from B:
// instead of one field growing into five, tapping a preset commits to a field
// set upfront (name always shown; the preset decides what else appears).
// ---------------------------------------------------------------------------

const PRESETS = [
  { key: "calories", label: "Just calories", fields: ["calories"] as FieldKey[] },
  { key: "cals_protein", label: "Cals + protein", fields: ["calories", "protein_g"] as FieldKey[] },
  { key: "full", label: "Full macros", fields: FIELDS.map((f) => f.key) },
];

function VariantC() {
  const [name, setName] = useState("");
  const [preset, setPreset] = useState<string | null>(null);
  const [values, setValues] = useState<Partial<Record<FieldKey, string>>>({});
  const [logged, setLogged] = useState<ReturnType<typeof toLogValues>[]>([]);

  const activeFields = PRESETS.find((p) => p.key === preset)?.fields ?? [];

  function save() {
    if (!name || !preset) return;
    setLogged((prev) => [toLogValues(name, values), ...prev]);
    setName("");
    setPreset(null);
    setValues({});
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>C — Preset chips pick the field set</h2>
      <p className="muted">
        Name, then a chip row picks how much detail you&apos;re bothering with — not a form that grows, a form
        that&apos;s chosen upfront.
      </p>

      <div style={{ border: "1px solid currentColor", borderRadius: "0.5rem", padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <input placeholder="Food name" value={name} onChange={(e) => setName(e.target.value)} style={{ fontWeight: 600 }} />

        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          {PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPreset(p.key)}
              style={{
                borderRadius: "999px",
                padding: "0.3rem 0.7rem",
                fontSize: "0.75rem",
                background: preset === p.key ? "#222" : "transparent",
                color: preset === p.key ? "#fff" : "inherit",
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {preset && (
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${activeFields.length}, 1fr)`, gap: "0.4rem" }}>
            {activeFields.map((key) => {
              const f = FIELDS.find((field) => field.key === key)!;
              return (
                <label key={key} style={{ fontSize: "0.65rem", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                  {f.label}
                  <input
                    type="number"
                    placeholder="—"
                    value={values[key] ?? ""}
                    onChange={(e) => setValues((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                </label>
              );
            })}
          </div>
        )}

        <button type="button" onClick={save} disabled={!name || !preset}>
          Log it
        </button>
      </div>

      <strong>Logged</strong>
      {logged.map((l, i) => (
        <div key={i} className="muted">
          {l.name}: {l.values.map((v) => `${v.trackable_key}=${v.value}`).join(", ") || "(no values)"}
        </div>
      ))}

      <StatePanel label="Variant C state" data={{ name, preset, values, logged }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Switcher
// ---------------------------------------------------------------------------

const VARIANTS = [
  { key: "A", name: "Full form up front", Component: VariantA },
  { key: "B", name: "Progressive disclosure", Component: VariantB },
  { key: "C", name: "Preset chips pick the field set", Component: VariantC },
] as const;

function PrototypeSwitcher({ current, onChange }: { current: string; onChange: (key: string) => void }) {
  const idx = VARIANTS.findIndex((v) => v.key === current);
  const active = VARIANTS[idx] ?? VARIANTS[0];

  return (
    <div
      style={{
        position: "fixed",
        bottom: "1rem",
        left: "50%",
        transform: "translateX(-50%)",
        background: "#222",
        color: "#fff",
        borderRadius: "999px",
        padding: "0.4rem 0.6rem",
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        boxShadow: "0 2px 12px rgba(0,0,0,0.35)",
        fontSize: "0.8rem",
        zIndex: 1000,
      }}
    >
      <button
        type="button"
        onClick={() => onChange((VARIANTS[(idx - 1 + VARIANTS.length) % VARIANTS.length] ?? VARIANTS[0]).key)}
        style={{ color: "#fff", border: "none" }}
      >
        ←
      </button>
      <span>
        {active.key} — {active.name}
      </span>
      <button
        type="button"
        onClick={() => onChange((VARIANTS[(idx + 1) % VARIANTS.length] ?? VARIANTS[0]).key)}
        style={{ color: "#fff", border: "none" }}
      >
        →
      </button>
    </div>
  );
}

export function PrototypeManualEntry() {
  const [variant, setVariant] = useState(() => new URLSearchParams(window.location.search).get("variant") ?? "A");

  function change(key: string) {
    setVariant(key);
    const url = new URL(window.location.href);
    url.searchParams.set("variant", key);
    window.history.replaceState(null, "", url);
  }

  const Active = VARIANTS.find((v) => v.key === variant)?.Component ?? VariantA;

  return (
    <main>
      <header>
        <h1>Manual food entry prototype</h1>
        <p className="muted">/prototype/manual-entry — throwaway, ticket #4 on the map (#1). No persistence.</p>
      </header>
      <Active />
      {!import.meta.env.PROD && <PrototypeSwitcher current={variant} onChange={change} />}
    </main>
  );
}
