import { headers } from "next/headers";
import { createClient } from "@/lib/supabase/server";
import { generateInvite } from "./actions";
import { ShareInviteButton } from "./ShareInviteButton";
import { Card } from "@/components/ui/Card";

async function getBaseUrl() {
  const h = await headers();
  const host = h.get("host");
  const proto = h.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

export default async function PartnerPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: link } = await supabase
    .from("partner_links")
    .select("user_id_a, user_id_b")
    .or(`user_id_a.eq.${user!.id},user_id_b.eq.${user!.id}`)
    .maybeSingle();

  if (link) {
    const partnerId = link.user_id_a === user!.id ? link.user_id_b : link.user_id_a;
    const { data: partner } = await supabase
      .from("partner_profile_public")
      .select("display_name")
      .eq("id", partnerId)
      .single();

    const { data: summary } = await supabase
      .rpc("get_partner_workout_summary", { target_partner_id: partnerId })
      .single();

    return (
      <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-8">
        <h1 className="font-display text-2xl font-semibold">
          {partner?.display_name ?? "Your partner"}
        </h1>

        {summary && (
          <>
            <div className="rounded-2xl bg-teal px-5 py-4 text-white">
              <div className="font-mono text-[11px] tracking-wide uppercase opacity-80">
                Current streak
              </div>
              <div className="mt-1 font-display text-4xl font-semibold">
                {summary.current_streak_days}
                <span className="ml-1 font-mono text-sm font-normal opacity-80">
                  {summary.current_streak_days === 1 ? "day" : "days"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Card className="text-center">
                <div className="font-display text-xl font-semibold">
                  {summary.workouts_last_7_days}
                </div>
                <div className="mt-1 font-mono text-[10px] tracking-wide text-ink-soft uppercase">
                  This week
                </div>
              </Card>
              <Card className="text-center">
                <div className="font-display text-xl font-semibold">
                  {summary.workouts_last_30_days}
                </div>
                <div className="mt-1 font-mono text-[10px] tracking-wide text-ink-soft uppercase">
                  This month
                </div>
              </Card>
              <Card className="text-center">
                <div className="font-display text-xl font-semibold">
                  {summary.total_workouts}
                </div>
                <div className="mt-1 font-mono text-[10px] tracking-wide text-ink-soft uppercase">
                  All time
                </div>
              </Card>
            </div>
          </>
        )}

        <p className="font-mono text-xs text-ink-soft">
          {summary?.last_workout_at
            ? `Last workout: ${new Date(summary.last_workout_at).toLocaleDateString()}`
            : "No workouts logged yet."}
        </p>
      </div>
    );
  }

  const { data: pendingInvite } = await supabase
    .from("partner_invites")
    .select("code")
    .eq("inviter_id", user!.id)
    .eq("status", "pending")
    .gt("expires_at", new Date().toISOString())
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const baseUrl = await getBaseUrl();

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-semibold">
        Invite your partner
      </h1>

      {pendingInvite ? (
        <>
          <p className="text-sm text-ink-soft">
            Share this link — it expires in 7 days.
          </p>
          <code className="rounded-xl border border-line bg-card px-3 py-2 font-mono text-sm break-all">
            {baseUrl}/invite/{pendingInvite.code}
          </code>
          <ShareInviteButton url={`${baseUrl}/invite/${pendingInvite.code}`} />
        </>
      ) : (
        <form action={generateInvite}>
          <button
            type="submit"
            className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
          >
            Generate invite link
          </button>
        </form>
      )}
    </div>
  );
}
