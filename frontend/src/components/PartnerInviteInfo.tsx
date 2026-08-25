import { InfoPopover } from "./InfoPopover";

const STEPS = [
  <>Copy the invite link below and send it to a friend</>,
  <>
    When they sign up through it, you're linked as <strong>accountability partners</strong>
  </>,
  <>You'll each see the other's workout streak, frequency, PRs, and nutrition streak</>,
];

/** Info icon next to the Partner heading; click reveals how partner invites work. */
export function PartnerInviteInfo() {
  return (
    <InfoPopover label="How partner invites work">
      <p className="info-popover-title">Invite a partner</p>
      <ol className="info-popover-steps">
        {STEPS.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      <p className="muted info-popover-footer">
        Your food logs and weight stay private — a partner never sees them, only the
        streak/PR summary above.
      </p>
    </InfoPopover>
  );
}
