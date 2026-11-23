import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ScaleIcon, SearchIcon, SendIcon, ThumbDownIcon, ThumbUpIcon } from "../components/icons";

describe("icons", () => {
  it("are decorative: hidden from assistive technology and never focusable", () => {
    for (const icon of [<SearchIcon key="s" />, <SendIcon key="a" />, <ThumbUpIcon key="u" />, <ThumbDownIcon key="d" />, <ScaleIcon key="c" />]) {
      const html = renderToStaticMarkup(icon);
      expect(html).toContain('aria-hidden="true"');
      expect(html).toContain('focusable="false"');
    }
  });
});
