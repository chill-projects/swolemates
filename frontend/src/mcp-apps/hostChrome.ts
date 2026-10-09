/**
 * How much chrome a component draws around itself, which depends on who's hosting it.
 *
 * In a chat host the bundle is the only thing on screen, so it supplies its own padding
 * and ground. In the SPA it's a grid item sitting beside real `.card` elements, and that
 * same padding insets its card ~14px relative to its siblings — the top and left edges
 * stop lining up with the cards above, below and next to it.
 *
 * So the host decides: `body.in-spa` drops the padding, and each bundle's stylesheet
 * says what that means for it. The alternative — cancelling the inset with a negative
 * margin on the iframe — would hard-code one bundle's padding into AppRenderer and
 * break the moment a bundle chose a different value.
 */

/** The name AppRenderer announces itself as over the AppBridge handshake. */
export const SPA_HOST = "swolemates-web";

export interface HostVersion {
  name: string;
  version: string;
}

/**
 * `getHostVersion()` is undefined before the handshake completes and in hosts that
 * don't implement it. Standalone chrome is the safe answer there: a component with too
 * much padding still reads fine, one with none is flush against the window edge.
 */
export function isSpaHost(host: HostVersion | null | undefined): boolean {
  return host?.name === SPA_HOST;
}

/** Marks the document so the bundle's own stylesheet can react. Returns the decision,
 *  since most callers want to branch on it for other host differences too. */
export function applyHostChrome(
  host: HostVersion | null | undefined,
  doc: Document = document,
): boolean {
  const inSpa = isSpaHost(host);
  doc.body.classList.toggle("in-spa", inSpa);
  return inSpa;
}
