import { useState } from "react";

import { useAddTmpxItem, useDeleteTmpxItem, useTmpxItems } from "../api/tmpx";

interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
}

export function TmpxPage({ me }: { me: Me }) {
  const [name, setName] = useState("");
  const [value, setValue] = useState(0);

  const items = useTmpxItems();
  const addItem = useAddTmpxItem();
  const deleteItem = useDeleteTmpxItem();

  return (
    <section>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          addItem.mutate(
            { name, value },
            {
              onSuccess: () => {
                setName("");
                setValue(0);
              },
            },
          );
        }}
      >
        <input
          aria-label="Item name"
          placeholder="Item name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          aria-label="Value"
          type="number"
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
        />
        <button type="submit" disabled={addItem.isPending || !name.trim()}>
          {addItem.isPending ? "Adding…" : "Add"}
        </button>
      </form>

      {items.isPending && <p className="muted">Loading…</p>}
      {items.isError && <p className="error">Couldn’t load items.</p>}

      {items.data && items.data.length === 0 && (
        <p className="muted">
          Nothing yet. Add one above, or ask Claude to run <code>tmpx_add</code> — both
          write to the same table.
        </p>
      )}

      <ul>
        {items.data?.map((item) => (
          <li key={item.id}>
            <span>
              {item.name} <span className="muted">· {item.value}</span>
            </span>
            <button
              type="button"
              onClick={() => deleteItem.mutate(item.id)}
              aria-label={`Delete ${item.name}`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
