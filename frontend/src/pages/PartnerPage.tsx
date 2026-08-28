import { useState } from "react";

import { usePartnerSummary } from "../api/partner";
import type { components } from "../api/generated";
import { PartnerInviteInfo } from "../components/PartnerInviteInfo";
import { formatInstant, useUserTimezone } from "../lib/datetime";
import { takeInviteRedeemError } from "./InvitePreviewPage";

type PartnerSummary = components["schemas"]["PartnerSummaryOut"];

/** Partner v1 (#5/#12, resolved): one accountability partner, linked via invite
 * code. Unlinked shows a "no partner" status with the invite link tucked behind the
 * heading's info icon (PartnerInviteInfo) rather than an always-visible card. Linked
 * shows the partner-safe aggregate summary — never food logs or weight, per the
 * privacy boundary in PartnerSummaryOut itself. */
export function PartnerPage() {
  const summary = usePartnerSummary();
  const [redeemError] = useState(() => takeInviteRedeemError());
  const unlinked = summary.data !== undefined && !summary.data;

  // App.tsx already supplies the .page-body padding around this route; .page-grid
  // only adds the stacking gap between the cards below.
  return (
    <div className="page-grid">
      <h2>
        Partner {unlinked && <PartnerInviteInfo />}
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
  return (
    <div className="card">
      <p className="muted">No partner added yet — tap the info icon above to invite one.</p>
    </div>
  );
}

function LinkedPartnerView({ summary }: { summary: PartnerSummary }) {
  const tz = useUserTimezone();
  return (
    <>
      <div className="card">
        <div className="card-header">
          <span className="card-title">{summary.partner_display_name ?? "Your partner"}</span>
          <span className="badge badge--plum">{summary.streak.weeks}-week streak</span>
        </div>
        <p className="card-note">
          <strong>
            {summary.streak.this_week} of {summary.streak.target}
          </strong>{" "}
          workouts this week
        </p>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Frequency</span>
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
            ? `Last workout: ${formatInstant(summary.frequency.last_workout_at, tz)}`
            : "No workouts logged yet."}
        </p>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Nutrition</span>
          <span className="badge badge--teal">{summary.nutrition_streak}-day streak</span>
        </div>
      </div>

      {summary.personal_records.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Personal records</span>
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
