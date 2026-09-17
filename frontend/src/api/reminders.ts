import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

const REMINDER_KEY = ["reminderSettings"] as const;
const PUSH_CONFIG_KEY = ["pushConfig"] as const;

/** Whether this deployment can send push at all, plus the VAPID public key the browser
 *  needs to subscribe. Public by design — it's the half of the pair that identifies us
 *  to the push service. Cached indefinitely: it only changes on redeploy. */
export function usePushConfig() {
  return useQuery({
    queryKey: PUSH_CONFIG_KEY,
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/reminders/config");
      if (error) throw new Error("Failed to read push config");
      return data;
    },
  });
}

export function useReminderSettings() {
  return useQuery({
    queryKey: REMINDER_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/reminders");
      if (error) throw new Error("Failed to load your reminder settings");
      return data;
    },
  });
}

export function useSetReminder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { enabled: boolean; hour?: number | null }) => {
      const { data, error } = await api.PUT("/api/reminders", {
        body: { enabled: body.enabled, hour: body.hour ?? null },
      });
      if (error) throw new Error("Failed to save that");
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: REMINDER_KEY }),
  });
}

/** base64url → the Uint8Array `pushManager.subscribe` wants. The VAPID key travels as
 *  base64url (no padding, `-`/`_`), which `atob` doesn't accept. */
function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  // Backed by an explicit ArrayBuffer: `Uint8Array.from` widens to ArrayBufferLike,
  // which `applicationServerKey` (BufferSource) won't accept since it could be shared.
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export class PushPermissionError extends Error {}

/**
 * Ask for notification permission and register this browser.
 *
 * Must be called from a real user gesture — iOS refuses otherwise, and Chrome now
 * ignores prompts that aren't. That's why this is a plain function the toggle calls
 * rather than something that runs on mount.
 */
export async function enablePush(publicKey: string): Promise<void> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new PushPermissionError(
      "This browser can't do push notifications. On iPhone, add Swolemates to your Home Screen first.",
    );
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new PushPermissionError(
      permission === "denied"
        ? "Notifications are blocked for this site — you'll need to allow them in your browser settings."
        : "Notifications weren't enabled.",
    );
  }

  const registration = await navigator.serviceWorker.ready;
  // `getSubscription` first: re-subscribing an already-subscribed browser with a
  // different key throws, and after a redeploy the existing one is usually still valid.
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    }));

  const { error } = await api.POST("/api/reminders/subscriptions", {
    body: subscription.toJSON() as { endpoint: string; keys: Record<string, string> },
  });
  if (error) throw new Error("Couldn't register this device for notifications");
}

/** Unregisters this browser server-side and drops the local subscription, so a device
 *  that's been turned off stops counting toward `subscribed_devices`. */
export async function disablePush(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;

  await api.DELETE("/api/reminders/subscriptions", {
    body: subscription.toJSON() as { endpoint: string; keys: Record<string, string> },
  });
  await subscription.unsubscribe();
}
