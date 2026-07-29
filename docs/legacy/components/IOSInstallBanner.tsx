"use client";

import { useEffect, useState } from "react";

const DISMISSED_KEY = "ios-install-banner-dismissed";

export function IOSInstallBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    const navigatorWithStandalone = window.navigator as Navigator & {
      standalone?: boolean;
    };
    const isStandalone =
      navigatorWithStandalone.standalone === true ||
      window.matchMedia("(display-mode: standalone)").matches;
    const dismissed = localStorage.getItem(DISMISSED_KEY);

    if (isIOS && !isStandalone && !dismissed) {
      // This reads browser-only APIs (UA, display-mode) that don't exist
      // during SSR, so there's no way to compute this during render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShow(true);
    }
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setShow(false);
  }

  if (!show) return null;

  return (
    <div className="flex items-center justify-between gap-3 bg-blue-50 px-4 py-2 text-sm text-blue-900">
      <span>
        Install this app: tap <strong>Share</strong>, then{" "}
        <strong>Add to Home Screen</strong>.
      </span>
      <button
        type="button"
        onClick={dismiss}
        className="shrink-0 underline"
      >
        Dismiss
      </button>
    </div>
  );
}
