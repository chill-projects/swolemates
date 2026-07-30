import { useCallback } from "react";

import { api } from "../api/client";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";

interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
}

/** Shape the REST rows into the same payload the MCP tools return, so the component
 *  can't tell which host it's running in. */
function toPayload(items: Array<{ id: string; name: string; value: number }>): ToolResultPayload {
  const payload = {
    items,
    summary:
      items.length === 0
        ? "No items yet."
        : `${items.length} item(s): ` + items.map((i) => `${i.name} (${i.value})`).join(", "),
  };
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

export function TmpxPage({ me }: { me: Me }) {
  const handleTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      switch (name) {
        case "tmpx_add": {
          const { error } = await api.POST("/api/tmpx", {
            body: { name: String(args.name ?? ""), value: Number(args.value ?? 0) },
          });
          if (error) throw new Error("add failed");
          break;
        }
        case "tmpx_delete": {
          const { error } = await api.DELETE("/api/tmpx/{item_id}", {
            params: { path: { item_id: String(args.item_id ?? "") } },
          });
          if (error) throw new Error("delete failed");
          break;
        }
        case "tmpx_list":
          break;
        default:
          throw new Error(`unknown tool: ${name}`);
      }
      const { data, error } = await api.GET("/api/tmpx");
      if (error || !data) throw new Error("list failed");
      return toPayload(data);
    },
    [],
  );

  return (
    <section>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>
      <AppRenderer bundleUrl="/mcp-apps/tmpx.html" initialTool="tmpx_list" onCallTool={handleTool} />
    </section>
  );
}
