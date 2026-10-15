import test from "node:test";
import assert from "node:assert/strict";
import { catalogPath, catalogPage } from "./lib/catalog-query.js";
test("three visible pages reuse a request; next group requests the next batch", () => {
  const args = { view: "recalls", term: "", recallFilters: { sort: "latest" } };
  assert.equal(
    catalogPath({ ...args, page: 0 }),
    catalogPath({ ...args, page: 2 }),
  );
  assert.notEqual(
    catalogPath({ ...args, page: 2 }),
    catalogPath({ ...args, page: 3 }),
  );
});
test("partial last group exposes only real pages and no next group", () => {
  const result = catalogPage(
    { items: Array.from({ length: 13 }, (_, i) => i), hasNext: false },
    "recalls",
    4,
  );
  assert.deepEqual(result.pageNumbers, [3, 4]);
  assert.deepEqual(result.items, [12]);
  assert.equal(result.hasNext, false);
  assert.equal(result.hasNextGroup, false);
});
