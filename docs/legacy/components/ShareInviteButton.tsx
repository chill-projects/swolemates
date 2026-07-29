"use client";

import { useState } from "react";

export function ShareInviteButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  async function handleShare() {
    if (navigator.share) {
      try {
        await navigator.share({ title: "Join me on Swolemates", url });
        return;
      } catch {
        // user cancelled the share sheet — fall through to clipboard copy
      }
    }
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      type="button"
      onClick={handleShare}
      className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
    >
      {copied ? "Copied!" : "Share invite link"}
    </button>
  );
}
