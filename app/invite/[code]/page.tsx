import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { acceptInvite } from "./actions";

export default async function InvitePage({
  params,
  searchParams,
}: {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { code } = await params;
  const { error } = await searchParams;

  const supabase = await createClient();

  const { data: preview } = await supabase
    .rpc("get_invite_preview", { invite_code: code })
    .single();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!preview?.valid) {
    return (
      <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
        <h1 className="font-display text-2xl font-semibold">
          Invite not valid
        </h1>
        <p className="text-sm text-ink-soft">
          This invite link has expired or was already used.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
      <h1 className="font-display text-2xl font-semibold">
        Connect with {preview.inviter_display_name}?
      </h1>

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      {user ? (
        <form action={acceptInvite.bind(null, code)}>
          <button
            type="submit"
            className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
          >
            Accept
          </button>
        </form>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-ink-soft">
            Log in or sign up, then come back to this link to accept.
          </p>
          <div className="flex gap-3">
            <Link
              href="/login"
              className="rounded-xl border border-line px-3 py-2 text-sm font-medium text-teal"
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="rounded-xl border border-line px-3 py-2 text-sm font-medium text-teal"
            >
              Sign up
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
