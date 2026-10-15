import test from "node:test";
import assert from "node:assert/strict";
import { readListState, listUrl, recallReturnUrl } from "./list-navigation.js";

test("recall page and filters survive a detail return URL", () => {
  const state = {
    view: "recalls",
    page: 2,
    term: "슬라임",
    source: "SAFETY_RECALL",
    from: "2026-09-01",
    to: "2026-10-15",
  };
  const url = listUrl(state);
  assert.equal(readListState(url.split("?")[1]).page, 2);
  assert.equal(recallReturnUrl("?returnTo=" + encodeURIComponent(url)), url);
});
test("invalid page, date and source values fall back safely", () => {
  const state = readListState("?page=-2&source=unknown&from=2026-02-30&to=bad");
  assert.equal(state.page, 0);
  assert.equal(state.source, "");
  assert.equal(state.from, "");
  assert.equal(state.to, "");
  assert.equal(readListState("?from=2026-10-15&to=2026-09-01").from, "");
});
test("detail return cannot redirect outside the recall list", () => {
  for (const url of [
    "https://example.com/?view=recalls",
    "//example.com/?view=recalls",
    "/?view=settings",
  ]) {
    assert.equal(
      recallReturnUrl("?returnTo=" + encodeURIComponent(url)),
      "/?view=recalls",
    );
  }
});
