import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EndingTag, StatusTag } from "../components/tags";
import { COPY } from "../lib/copy";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-23T03:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("ending tags", () => {
  it("names the ending document of a confirmed ending", () => {
    const html = renderToStaticMarkup(<EndingTag ending={{ ended_on: "2022-07-01", end_basis: "explicit", ended_by: "78/2021/TT-BTC" }} copy={COPY.en} />);
    expect(html).toContain("Ended 01/07/2022 · by 78/2021/TT-BTC");
    expect(html).toContain("status-expired");
  });

  it("flags an inferred ending as possible, in Vietnamese too", () => {
    const ending = { ended_on: "2025-07-01", end_basis: "guidance", ended_by: "13/2008/QH12" };
    expect(renderToStaticMarkup(<EndingTag ending={ending} copy={COPY.en} />)).toContain("May have ended 01/07/2025 · guides 13/2008/QH12, which ended");
    expect(renderToStaticMarkup(<EndingTag ending={ending} copy={COPY.vi} />)).toContain("Có thể đã hết hiệu lực từ 01/07/2025");
  });

  it("shows nothing without an ending", () => {
    expect(renderToStaticMarkup(<EndingTag ending={{}} copy={COPY.en} />)).toBe("");
  });

  it("hides the ministry's 'in force' once a confirmed ending has passed", () => {
    const ended = { ended_on: "2022-07-01", end_basis: "explicit" };
    expect(renderToStaticMarkup(<StatusTag status="EFFECTIVE" ending={ended} copy={COPY.en} />)).toBe("");
    expect(renderToStaticMarkup(<StatusTag status="EFFECTIVE" copy={COPY.en} />)).toContain("In force");
    expect(renderToStaticMarkup(<StatusTag status="EXPIRED" ending={ended} copy={COPY.en} />)).toContain("Expired");
  });
});
