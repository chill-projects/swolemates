import { useEffect, useRef, useState } from "react";

import { useGenerateInvite, usePartnerSummary } from "../api/partner";
import type { components } from "../api/generated";
import { PartnerInviteInfo } from "../components/PartnerInviteInfo";
import { takeInviteRedeemError } from "./InvitePreviewPage";

type PartnerSummary = components["schemas"]["PartnerSummaryOut"];

/** Partner v1 (#5/#12, resolved): one accountability partner, linked via invite
 * code. Unlinked shows a share link (auto-generated on mount — generateInvite is
 * idempotent server-side, returns the same pending invite on repeat visits rather
 * than minting a new code). Linked shows the partner-safe aggregate summary — never
 * food logs or weight, per the privacy boundary in PartnerSummaryOut itself. */
export function PartnerPage() {
  const summary = usePartnerSummary();
  const [redeemError] = useState(() => takeInviteRedeemError());

  return (
    <div className="dash-stack">
      <h2>
        Partner <PartnerInviteInfo />
      </h2>
      {redeemError && <p className="error">{redeemError}</p>}
      {summary.isPending && <p className="muted">Loading…</p>}
      {summary.isError && <p className="error">Couldn’t load your partner.</p>}
      {summary.data !== undefined &&
        (summary.data ? <LinkedPartnerView summary={summary.data} /> : <InviteView />)}
    </div>
  );
}

function InviteView() {
  const generate = useGenerateInvite();
  const triggered = useRef(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (triggered.current) return;
    triggered.current = true;
    generate.mutate();
  }, [generate]);

  if (generate.isError) return <p className="error">{generate.error.message}</p>;
  if (!generate.data) return <p className="muted">Setting up your invite link…</p>;

  const url = `${window.location.origin}/invite/${generate.data.code}`;

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <span className="dash-card-title">Invite a partner</span>
      </div>
      <p className="muted">
        Share this link — whoever signs up through it becomes your accountability partner.
        They’ll see your workout streak, frequency, PRs, and nutrition streak — never your
        food logs or weight.
      </p>
      <div className="partner-invite-row">
        <code>{url}</code>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(url).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            });
          }}
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <p className="muted">
        Expires {new Date(generate.data.expires_at).toLocaleDateString()}
      </p>
    </div>
  );
}

function LinkedPartnerView({ summary }: { summary: PartnerSummary }) {
  return (
    <>
      <div className="dash-card">
        <div className="dash-card-header">
          <span className="dash-card-title">{summary.partner_display_name ?? "Your partner"}</span>
          <span className="dash-badge dash-badge--plum">{summary.streak.weeks}-week streak</span>
        </div>
        <p className="dash-week-detail">
          <strong>
            {summary.streak.this_week} of {summary.streak.target}
          </strong>{" "}
          workouts this week
        </p>
      </div>

      <div className="dash-card">
        <div className="dash-card-header">
          <span className="dash-card-title">Frequency</span>
        </div>
        <div className="partner-stat-row">
          <div className="partner-stat">
            <strong>{summary.frequency.workouts_last_7_days}</strong>
            <span>Last 7 days</span>
          </div>
          <div className="partner-stat">
            <strong>{summary.frequency.workouts_last_30_days}</strong>
            <span>Last 30 days</span>
          </div>
          <div className="partner-stat">
            <strong>{summary.frequency.total_workouts}</strong>
            <span>All time</span>
          </div>
        </div>
        <p className="muted">
          {summary.frequency.last_workout_at
            ? `Last workout: ${new Date(summary.frequency.last_workout_at).toLocaleDateString()}`
            : "No workouts logged yet."}
        </p>
      </div>

      <div className="dash-card">
        <div className="dash-card-header">
          <span className="dash-card-title">Nutrition</span>
          <span className="dash-badge dash-badge--teal">{summary.nutrition_streak}-day streak</span>
        </div>
      </div>

      {summary.personal_records.length > 0 && (
        <div className="dash-card">
          <div className="dash-card-header">
            <span className="dash-card-title">Personal records</span>
          </div>
          <ul>
            {summary.personal_records.map((pr, i) => (
              <li key={i}>
                <span>
                  {pr.exercise_name} ({pr.kind === "e1rm" ? "e1RM" : "weight"})
                </span>
                <span>
                  {pr.value}
                  {pr.kind === "weight" ? " lb" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
