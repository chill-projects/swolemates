import { ImageResponse } from "next/og.js";
import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const publicDir = path.join(process.cwd(), "public");
await mkdir(publicDir, { recursive: true });

async function generate(filename, size, { padding = 0 } = {}) {
  const inner = size - padding * 2;
  const response = new ImageResponse(
    {
      type: "div",
      props: {
        style: {
          width: size,
          height: size,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#111827",
        },
        children: {
          type: "div",
          props: {
            style: {
              width: inner,
              height: inner,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: inner * 0.55,
            },
            children: "💪",
          },
        },
      },
    },
    { width: size, height: size },
  );

  const buffer = Buffer.from(await response.arrayBuffer());
  await writeFile(path.join(publicDir, filename), buffer);
  console.log(`wrote ${filename} (${size}x${size})`);
}

await generate("icon-192.png", 192);
await generate("icon-512.png", 512);
// Maskable icons need padding so the shape survives being cropped to a circle/squircle by the OS.
await generate("icon-maskable-512.png", 512, { padding: 64 });
await generate("apple-touch-icon.png", 180);
