/**
 * The TmpX component. Renders in two hosts from this one bundle:
 *  - Claude, via the `ui://swolemates/tmpx.html` MCP resource
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * All host communication goes through the ext-apps protocol: results arrive via
 * ontoolresult, actions go out via callServerTool. No direct network access — the
 * iframe CSP forbids it, and that's the property that makes the bundle portable.
 */

import { App } from "@modelcontextprotocol/ext-apps";

interface TmpxItem {
  id: string;
  name: string;
  value: number;
  created_at: string;
}

interface TmpxPayload {
  items: TmpxItem[];
  summary: string;
}

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const listEl = $<HTMLUListElement>("items");
const nameInput = $<HTMLInputElement>("name");
const valueInput = $<HTMLInputElement>("value");
const addBtn = $<HTMLButtonElement>("add-btn");

const app = new App({ name: "Swolemates TmpX", version: "1.0.0" });

function extractPayload(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): TmpxPayload | null {
  const structured = result.structuredContent as TmpxPayload | undefined;
  if (structured && Array.isArray(structured.items)) return structured;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as TmpxPayload;
    return Array.isArray(parsed.items) ? parsed : null;
  } catch {
    return null;
  }
}

function render(payload: TmpxPayload): void {
  statusEl.textContent = payload.items.length === 0 ? "No items yet — add one." : "";
  listEl.replaceChildren(
    ...payload.items.map((item) => {
      const li = document.createElement("li");

      const label = document.createElement("span");
      label.textContent = `${item.name} `;
      const value = document.createElement("span");
      value.className = "muted";
      value.textContent = `· ${item.value}`;
      label.appendChild(value);

      const del = document.createElement("button");
      del.type = "button";
      del.textContent = "×";
      del.setAttribute("aria-label", `Delete ${item.name}`);
      del.onclick = () => {
        void callAndRender("tmpx_delete", { item_id: item.id });
      };

      li.append(label, del);
      return li;
    }),
  );
}

async function callAndRender(name: string, args: Record<string, unknown>): Promise<void> {
  addBtn.disabled = true;
  try {
    const result = await app.callServerTool({ name, arguments: args });
    const payload = extractPayload(result);
    if (payload) render(payload);
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  } finally {
    addBtn.disabled = false;
  }
}

// Not a form submit: sandboxed iframes without allow-forms swallow those silently.
function addItem(): void {
  const name = nameInput.value.trim();
  if (!name) return;
  void callAndRender("tmpx_add", { name, value: Number(valueInput.value) || 0 }).then(() => {
    nameInput.value = "";
    valueInput.value = "0";
  });
}

addBtn.onclick = addItem;
for (const input of [nameInput, valueInput]) {
  input.onkeydown = (event) => {
    if (event.key === "Enter") addItem();
  };
}

// The host pushes the originating tool's result (e.g. tmpx_list) once on render.
app.ontoolresult = (result) => {
  const payload = extractPayload(result);
  if (payload) render(payload);
  else statusEl.textContent = "Waiting for data…";
};

await app.connect();
statusEl.textContent = "Loading…";
