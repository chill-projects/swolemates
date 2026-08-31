/**
 * Every component bundle runs in two hosts: Claude, where `callServerTool`
 * reaches the real MCP tool, and the SPA, where AppRenderer's `onCallTool`
 * hands it to a host page that stands in for the server with REST calls. The
 * two are wired by hand and nothing links them, so a tool added to a component
 * can quietly have no branch on the SPA side — it works in chat and throws
 * "unknown tool" in the app. That drift shipped three times in the nutrition
 * component before this test existed.
 *
 * This is a source scan, not a runtime check: it reads which tool names each
 * component calls and which ones its host page dispatches, and asserts the
 * first set is covered by the second. It can't verify that a branch forwards
 * every *argument* correctly (also a real failure mode — see the
 * log_meal_template multiplier/meal_type drop) — only that a branch exists.
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/** Which host page stands in for the MCP server for each bundle. PlanPage
 *  hosts two, with a separate handler for each. */
const HOSTS = [
  { component: "nutrition-day", page: "NutritionPage" },
  { component: "planned", page: "PlanPage" },
  { component: "template", page: "PlanPage" },
  { component: "workout-live", page: "WorkoutLivePage" },
];

const read = (relative: string) =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

const matchAll = (source: string, pattern: RegExp): string[] =>
  [...source.matchAll(pattern)].map((m) => m[1] as string);

/** Tool names a component asks its host to call. */
function toolsCalledBy(component: string): string[] {
  const source = read(`./${component}/main.ts`);
  return [
    ...new Set([
      ...matchAll(source, /callAndRender\(\s*"([a-z_]+)"/g),
      ...matchAll(source, /callServerTool\(\{\s*name:\s*"([a-z_]+)"/g),
    ]),
  ].sort();
}

/** Tool names a page dispatches. Both forms are in use: a `case` in the
 *  handler's switch, and an early `if (name === ...)` guard for the tools that
 *  return their own payload instead of falling through to a refetch. */
function toolsDispatchedBy(page: string): Set<string> {
  const source = read(`../pages/${page}.tsx`);
  return new Set([
    ...matchAll(source, /case\s+"([a-z_]+)"/g),
    ...matchAll(source, /name === "([a-z_]+)"/g),
  ]);
}

describe.each(HOSTS)("$component in $page", ({ component, page }) => {
  it("dispatches every tool the component calls", () => {
    const called = toolsCalledBy(component);
    // Guard against the scan silently matching nothing (a changed call style
    // would otherwise make this whole test vacuously pass).
    expect(called.length).toBeGreaterThan(0);

    const dispatched = toolsDispatchedBy(page);
    expect(called.filter((tool) => !dispatched.has(tool))).toEqual([]);
  });
});

it("covers every component bundle", () => {
  const bundles = readdirSync(dirname(fileURLToPath(import.meta.url)), {
    withFileTypes: true,
  })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  // A new bundle has to be added to HOSTS above, or it'd be exempt from the
  // parity check without anyone noticing.
  expect(bundles).toEqual([...new Set(HOSTS.map((h) => h.component))].sort());
});
