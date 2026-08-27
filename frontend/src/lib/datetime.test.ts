import { describe, expect, it } from "vitest";

import { dateFromIso, daysBetween, isoDateInTz, isoFromDate, todayIsoInTz } from "./datetime";

describe("isoDateInTz", () => {
  it("buckets an instant into the calendar day of the given zone", () => {
    // 2026-08-26T03:00Z is still 2026-08-25 in Los Angeles (PDT, UTC-7)
    const instant = "2026-08-26T03:00:00Z";
    expect(isoDateInTz(instant, "America/Los_Angeles")).toBe("2026-08-25");
    expect(isoDateInTz(instant, "UTC")).toBe("2026-08-26");
    expect(isoDateInTz(instant, "Asia/Tokyo")).toBe("2026-08-26"); // UTC+9 → noon
  });

  it("accepts Date and epoch-millis too", () => {
    const d = new Date("2026-01-01T00:30:00Z");
    expect(isoDateInTz(d, "America/New_York")).toBe("2025-12-31");
    expect(isoDateInTz(d.getTime(), "UTC")).toBe("2026-01-01");
  });
});

describe("dateFromIso / isoFromDate", () => {
  it("round-trips a calendar date through a local-midnight Date", () => {
    const d = dateFromIso("2026-08-27");
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(7);
    expect(d.getDate()).toBe(27);
    expect(isoFromDate(d)).toBe("2026-08-27");
  });
});

describe("daysBetween", () => {
  it("counts whole calendar days, order-sensitive", () => {
    expect(daysBetween("2026-08-25", "2026-08-27")).toBe(2);
    expect(daysBetween("2026-08-27", "2026-08-25")).toBe(-2);
    expect(daysBetween("2026-02-28", "2026-03-01")).toBe(1); // 2026 is not a leap year
  });
});

describe("todayIsoInTz", () => {
  it("returns a well-formed date matching Intl for the zone", () => {
    const expected = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Australia/Sydney",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
    expect(todayIsoInTz("Australia/Sydney")).toBe(expected);
  });
});
