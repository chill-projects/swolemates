import { useEffect, useState } from "react";

const DISMISSED_KEY = "ios-install-banner-dismissed";

/** iOS never shows an automatic install prompt (no `beforeinstallprompt` equivalent) —
 *  this is the only way iOS users discover Add to Home Screen at all. Ported from
 *  docs/legacy/components/IOSInstallBanner.tsx. */
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
      setShow(true);
    }
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setShow(false);
  }

  if (!show) return null;

  return (
    <div className="ios-install-banner">
      <span>
        Install this app: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
      </span>
      <button type="button" onClick={dismiss}>
        Dismiss
      </button>
    </div>
  );
}
