# Research: getting Apple Watch workout data into Swolemates automatically

**Status:** Research only — no implementation. Verified 2026-08-18.

## TL;DR

There is no way to get HealthKit data into a backend without code that runs *on the device*,
because HealthKit has no web/cloud API (§1). The good news: that on-device code does not have to
be an app Swolemates ships. iOS Shortcuts' built-in **Apple Watch Workout** automation trigger,
combined with the **Get Contents of URL** action, can POST a completed workout's calories/HR/
duration/type to a webhook fully on-device, with no App Store submission, no developer account,
and no new code in this repo (§2). That's the recommended starting point. Health Auto Export is a
stronger fallback if the trigger proves flaky, at $6.99/yr (§3). A native SwiftUI bridge app is
technically possible on a free Apple ID for two personal phones (§4) — but **do not reach for it
first**, see the flag immediately below.

## Flag: any native-app option reopens the PWA-vs-React-Native decision — do not slide into this

`PRD.md` §3 is explicit about why this app is a PWA and not React Native:

> "No wearable/HealthKit integration is planned, which removes the main reason to go native. PWA
> avoids the $99/yr Apple Developer fee and app-store review, and iterates faster for a two-person
> coding-practice project."

Section 4 of this doc shows that a minimal SwiftUI HealthKit-reader app is *feasible* for two
personal phones without paid enrollment or App Store review — but building **any** native app,
even a tiny single-purpose bridge with no App Store presence, is still new Swift code, a second
Xcode project, and a second install/update mechanism (7-day re-signing under free provisioning,
see §4) that this repo does not otherwise need. That is a real ongoing maintenance cost the PRD's
"why PWA" reasoning was written to avoid, even though it wouldn't literally touch the $99/yr fee
or App Store review it names. **Treat "build a native bridge app" as its own decision requiring
explicit discussion, not a detail to fold into a workout-sync ticket.** The recommendation below
avoids it entirely for now.

## 1. HealthKit is native-only — confirmed

Apple's own framework page states HealthKit's scope directly:

> "HealthKit provides a central repository for health and fitness data for iPhone, iPad, Apple
> Watch, and Apple Vision Pro." — <https://developer.apple.com/health-fitness/>

No macOS, no web, no JavaScript surface is listed. The framework's reference docs
(<https://developer.apple.com/documentation/healthkit>) are Swift/Objective-C API only — every
HealthKit class (`HKHealthStore`, `HKWorkout`, `HKQuery`, …) is consumed via the iOS/iPadOS/
watchOS/visionOS SDKs in Xcode. There is no HealthKit REST endpoint, no OAuth-style token you can
exchange server-side, and no cloud copy of HealthKit data Apple operates — the data lives in an
encrypted on-device store, full stop. Any integration path is therefore constrained to: **code
that runs on the phone reads HealthKit, then that code sends the data somewhere else.** Every
option below is a variation on that one constraint.

## 2. iOS Shortcuts as a bridge — confirmed precisely

### The only Health/workout automation trigger that exists today

Apple's Shortcuts user guide enumerates automation trigger categories exhaustively: **Event
triggers, Travel triggers, Communication triggers, Transaction triggers, Setting triggers**
(<https://support.apple.com/guide/shortcuts/setting-triggers-apde31e9638b/ios>). There is no
"Health" category and no generic "new workout saved to Health" or "new HealthKit sample" trigger.

The one workout-relevant trigger, under **Event triggers**, is **Apple Watch Workout**
(<https://support.apple.com/guide/shortcuts/event-triggers-apd932ff833f/ios>):

> "Choose one or more workout types to launch your automation (or choose Any Workout)."
> "Choose when in your workout you want to run your automation. There are three options: Start,
> End, or Starts or Ends."

This requires the workout to be run on a paired Apple Watch (matches the "when available"
framing — it simply won't fire on days the watch isn't worn, which is fine).

### What data a Shortcuts workout action can pull

Apple's official action-level docs are JS-rendered and didn't fetch cleanly, so this is
corroborated rather than independently quoted from Apple: community/reference documentation
(Matthew Cassinelli, a widely-cited ex-Shortcuts-team documenter,
<https://matthewcassinelli.com/actions/log-health-sample/>) and a working example
(<https://blog.maximeheckel.com/posts/build-personal-health-api-shortcuts-serverless/>) confirm a
**Find Health Samples** action can pull active/total calories, average heart rate, and workout
duration/type from a completed workout, with results assembled into a dictionary for the next
action.

### Foreground/background requirement — the real limitation

> "The shortcut cannot run in the background while the phone is locked. Apple Health data (or
> HealthKit data) can only be read while the phone is unlocked."
> — <https://blog.maximeheckel.com/posts/build-personal-health-api-shortcuts-serverless/>

This is corroborated by Health Auto Export's own FAQ making the identical claim independently
(§3) — it's a HealthKit-level OS restriction, not an app bug. Practically: the automation fires,
iOS queues it, and it completes the next time the phone is unlocked (checking a notification,
picking it up) rather than instantly in the background. For two users who are "fine with a few
minutes of lag," this is acceptable — a phone is unlocked within minutes of most workouts ending.

Confirmed separately: **Ask Before Running** can be turned off so the automation runs with no
confirmation tap —

> "Turn off Ask Before Running, then tap Don't Ask... The automation will not notify you when
> it's triggered." — <https://support.apple.com/guide/shortcuts/enable-or-disable-a-personal-automation-apd602971e63/ios>

so the whole thing is silent once configured (no daily "run this shortcut?" prompts).

### Permission friction

Not independently confirmed via a primary Apple page (Shortcuts' own HealthKit-authorization
sheet is documented only in community threads, e.g. Apple Community discussions on granting
Shortcuts Health access). Expected shape, consistent with all HealthKit apps: a one-time,
per-data-type authorization sheet the first time the shortcut runs (toggle Steps/Heart
Rate/Workouts/etc individually) — a few seconds of setup once per user, not per-run friction.

### HTTP POST to an arbitrary webhook — confirmed, zero developer account needed

**Get Contents of URL** supports POST, custom headers, and a JSON body built from prior actions'
output — entirely configured on-device in the Shortcuts app, no App Store submission, no Apple
Developer Program enrollment of any kind. This is standard, widely-documented Shortcuts
functionality (e.g. IFTTT's own integration guide treats it as a given:
<https://ifttt.com/connect/ios_shortcuts/maker_webhooks>).

## 3. Third-party bridge apps — Health Auto Export, verified

**Correction to the brief:** the App Store listing
(<https://apps.apple.com/us/app/health-auto-export-json-csv/id1115567069>) shows the current
developer/seller as **Lybron Sobers**, not Vitalii Andrusyshyn — the app appears to have changed
hands or that attribution is stale. Current docs live at `help.healthyapps.dev` (brand
"HealthyApps").

### Pricing (App Store listing, live)

| Tier | Price |
|---|---|
| Free | $0, limited |
| Basic | $2.99 one-time |
| Premium — monthly | $1.99/mo |
| Premium — annual | $6.99/yr |
| Premium — lifetime | $24.99 one-time |

**REST API / webhook automation is a Premium feature** —
<https://help.healthyapps.dev/en/health-auto-export/faq/>:
> "Premium includes: All free and Basic features... Auto-export data to REST APIs, iCloud Drive,
> Google Drive, Dropbox, MQTT, Home Assistant, and Calendar on iPhone."

At $6.99/yr for annual Premium (or $24.99 once, lifetime), this is trivially affordable for two
personal users.

### Push vs. batch, and the same phone-unlock constraint

It is **not** a true real-time push. Automations run on a configured interval and depend on iOS
background execution:

> "Configure how often the automation should upload data: Select a number and interval."
> "Automations rely on Background App Refresh and may not run immediately if: Background App
> Refresh is disabled for the app, The device is in Low Power Mode..."
> — <https://help.healthyapps.dev/en/health-auto-export/automations/rest-api/>

> "iOS only allows apps to access Apple Health data: When your iPhone is unlocked. When iOS
> grants background execution time." — <https://help.healthyapps.dev/en/health-auto-export/faq/>

Same underlying HealthKit constraint as the Shortcuts approach — not a weakness specific to this
app, and again fine for a "minutes of lag is OK" requirement.

### Auth scheme and payload shape for a receiving backend

Custom HTTP headers, explicitly documented for auth:

> "Add custom HTTP headers for authentication or metadata. Common use cases include: API keys:
> `X-API-Key: your-api-key`, Authorization tokens: `Authorization: Bearer your-token`."
> — <https://help.healthyapps.dev/en/health-auto-export/automations/rest-api/>

Workout JSON (v2 format), field names confirmed at
<https://help.healthyapps.dev/en/health-auto-export/export-format/workouts/>:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Running",
  "start": "2024-02-06 07:00:00 -0800",
  "end": "2024-02-06 07:30:00 -0800",
  "duration": 1800,
  "activeEnergyBurned": { "qty": 350, "units": "kcal" },
  "totalEnergy": { "qty": 450, "units": "kcal" },
  "avgHeartRate": { "qty": 150, "units": "bpm" },
  "heartRateData": [
    { "date": "2024-02-06 07:00:00 -0800", "Min": 120, "Avg": 150, "Max": 175,
      "units": "bpm", "source": "Apple Watch" }
  ]
}
```

Optional fields (heart rate, energy) "are only included when data is available" — matches the
"when available" requirement directly; a workout logged without a worn watch just omits HR.

### Current strongest alternative?

A 2026 third-party comparison (secondary, corroborating only — not independently verified)
consistently ranks Health Auto Export as the leading option specifically for REST API/webhook
automation, with competitors (HealthSave, HealthFit) positioned around privacy-dashboard or
workout-detail use cases instead. No stronger automation-focused alternative surfaced.

## 4. A minimal native SwiftUI bridge, without App Store distribution — verified precisely

This section exists to answer the brief's question rigorously; §2 above is still the
recommendation, per the flag at the top of this doc.

### Cost and what it unlocks

$99 USD/year — <https://developer.apple.com/support/compare-memberships/>. Paid membership is
required for: **App Store distribution**, App Store Connect (which gates TestFlight — see below),
Ad hoc distribution, and several other items. It is **not** required for the HealthKit
entitlement itself (next point).

### HealthKit entitlement on a free ("Personal Team") account — the surprising, verified answer

The brief called this out as "often restricted — verify precisely, don't assume." It turned out
**not** to be restricted. Apple's own capabilities reference table
(<https://developer.apple.com/help/account/reference/supported-capabilities-ios/>) lists three
account columns — **ADP** (paid Program), **ADEP** (paid Enterprise Program), and **Apple
Developer** (free, no-cost agreement, "developers can't distribute apps") — and shows:

| Capability | ADP | ADEP | Apple Developer (free) |
|---|---|---|---|
| HealthKit | ✓ | ✓ | ✓ |
| HealthKit Estimate Recalibration | ✓ | ✓ | ✓ |

No "development only" footnote is attached to either HealthKit row (several other capabilities on
the same page, e.g. Family Controls, do carry that footnote — so its absence here is meaningful,
not an oversight). **The HealthKit entitlement works under free personal-team signing**, for
running the app on your own device via Xcode. This directly enables the "install via Xcode
direct-to-device for 2 personal iPhones, no paid enrollment" path the brief asked about.

### Free personal-team limits (all fit two personal phones easily)

From Apple's own membership-comparison page
(<https://developer.apple.com/support/compare-memberships/>):

> "The number of App IDs that can be registered to your account at one time is limited to 10 and
> each expires after 7 days."
> "The number of test devices that can be registered to your account for each platform is limited
> to 3 and each expires after 7 days."
> "Provisioning profiles will expire 7 days from issuance, which may require you to rebuild and
> re-install your app to your device after expiration."

3 devices per platform comfortably covers 2 personal iPhones. The real cost is the **7-day
re-signing requirement** — someone has to plug each phone into a Mac and hit "Run" in Xcode at
least weekly forever, or the bridge app silently stops launching. That's an ongoing manual chore
this repo's "when available, minutes of lag is fine" bar doesn't require anyone to accept.

### TestFlight

Requires the paid Program — TestFlight is bundled into App Store Connect access, which is an
ADP-only benefit (confirmed on the membership comparison table, and directly:
<https://developer.apple.com/testflight/>):

> "Designate up to 100 members of your development team who hold the Account Holder, Admin, App
> Manager, Developer, or Marketing role as beta testers."

Those are App Store Connect team roles, which require the $99/yr Program. So: **free personal-
team Xcode-to-device install works without paying; TestFlight does not** — if the weekly re-sign
chore of free provisioning is unacceptable, the fallback isn't "free TestFlight," it's "$99/yr
Program membership," not a smaller free tier.

## 5. Other 2026 considerations

**No new Apple-published web-facing health data standard exists.** Nothing found contradicts
§1 — HealthKit access remains device-native only.

**Recent Shortcuts changes (iOS 26):** per secondary coverage (9to5Mac, Matthew Cassinelli — not
independently confirmed via a primary Apple page, which returned only a truncated/JS-rendered
response), iOS 26 added three new automation trigger types — screenshot, keyboard connection, and
notification-content triggers — plus a set of Apple Intelligence actions. None of this coverage
mentions a new Health/workout-specific trigger; **Apple Watch Workout** (§2) remains the only one.

**Apple Health Records / FHIR — confirmed red herring, doesn't apply here.** Health Records is a
clinical-records feature: it connects a patient's iPhone to a hospital/clinic's EHR system via
SMART-on-FHIR OAuth to pull lab results, conditions, medications, and immunizations from that
institution (FHIR R4 / US Core v3.1.1) —
<https://support.apple.com/guide/healthregister/technical-requirements-specifications-health-apd12d144779/web>.
It has nothing to do with workout/fitness metrics generated by an Apple Watch, and there is no
path from it to calories/HR/duration data. Confirmed not relevant.

**Wearable-data aggregator platforms (Terra, Spike, etc.) — confirmed disproportionate, and don't
even remove the native-app requirement.** Terra's own integration docs state the core constraint
plainly:

> "Apple Health has no web API, so you connect through the Terra mobile SDK in Swift, React
> Native, or Flutter... Once connected, Terra pushes every synced payload to your webhook."
> — <https://tryterra.co/integrations/apple-health>

I.e. you still build and ship a native (or React Native) app embedding their SDK — Terra
replaces "build your own ingestion backend" with "pay Terra to host normalization," it does not
remove the native-app requirement §1 establishes. And the price is wildly disproportionate for
two personal users:

- Terra: **$499/mo** (or $399/mo billed annually), no free tier — <https://tryterra.co/pricing>
- Spike API: **$450/mo**, no free tier — <https://www.spikeapi.com/pricing>

Both are B2B platforms priced for apps with hundreds-to-thousands of end users. Confirmed
disproportionate; not worth pursuing at this scale.

## Recommendation

**Ship Shortcuts automation now. Do not build a native bridge app.** Revisit Health Auto Export
only if the raw Shortcuts automation proves flaky in practice for either user.

Why, against the actual constraints:

- **2 technical personal users, watch not always worn:** the Apple Watch Workout trigger only
  fires when a workout was actually recorded on the watch — exactly the "when available"
  semantics wanted, for free, with zero new code.
- **Minutes of lag OK:** the phone-must-be-unlocked HealthKit constraint (§2, §3) is a non-issue
  at that tolerance, and it's identical across every device-based option — there's no path that
  avoids it, so it's not a reason to prefer one option over another.
- **No manual copy-paste:** satisfied — the whole point of the trigger + POST chain.
- **Avoid reopening PWA-vs-RN:** Shortcuts requires writing zero Swift, shipping no app, and
  touching no Xcode project. It is the only option in this doc that carries no native-app
  footprint at all. Health Auto Export is a very close second on this axis (an App Store app the
  two users install, but still zero code Swolemates owns or ships). A native bridge app is the
  only option that reopens the PRD decision, and it's the one to avoid.
- **Fallback ordering:** if Apple Watch Workout automations turn out to be unreliable (missed
  triggers, iOS killing the automation) for either user in practice, move to Health Auto Export
  next ($6.99/yr, same webhook shape, more mature scheduling/retry behavior) before ever
  considering a native bridge — it's a $6.99/yr App Store install, not a new codebase.

### Backend sketch (for a later design conversation — not a spec)

- A new endpoint under `app/api/`, e.g. `POST /api/integrations/healthkit-workout` (or a more
  generic `workout-ingest`, since Health Auto Export and a hand-rolled Shortcut would post a
  similar shape) — thin router, all logic in a service function per `AGENTS.md`'s "routers
  contain no logic" rule.
- **Auth doesn't fit the existing WorkOS/AuthKit model** — Shortcuts and Health Auto Export can't
  do an interactive OAuth redirect. The natural fit is a per-user, long-lived opaque bearer
  token/webhook secret (issued once from account settings, revocable, sent as `Authorization:
  Bearer <token>` or `X-API-Key`, matching what Health Auto Export's own auth-header mechanism
  and a Shortcuts "Get Contents of URL" header both already support natively) — mapped
  server-side to a `user_id`, so the existing "every query filters by `user_id`" rule in
  `AGENTS.md` still holds even though the caller isn't a WorkOS session.
- **Data model:** likely a small ingestion table (or fields added to the existing workout
  tables) capturing `source` ("healthkit-shortcuts" / "health-auto-export"), `external_id` (for
  idempotency — both sources can resend the same workout), `calories_active`,
  `calories_total`, `avg_heart_rate`, `duration_seconds`, `workout_type`, `started_at`,
  `ended_at`. Whether ingested workouts merge into the existing `workouts` table as a
  watch-sourced row, or land in a separate table surfaced as supplementary context on an
  existing manually-logged workout, is a real design question for that later conversation —
  this doc isn't resolving it.
- Given the payload shapes already confirmed in §2–§3, both the Shortcuts JSON body and Health
  Auto Export's JSON body can realistically map onto the same ingestion shape, so the endpoint
  doesn't need to special-case which bridge sent it.
