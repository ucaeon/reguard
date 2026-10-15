import test from "node:test";
import assert from "node:assert/strict";
import { loadOwnedProducts, ownedCategory } from "./items/owned-products.js";
test("loads all saved pages with account credentials", async () => {
  const calls = [];
  const request = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      json: async () => ({
        items: [{ id: calls.length }],
        hasNext: calls.length === 1,
      }),
    };
  };
  assert.deepEqual(await loadOwnedProducts(undefined, request), [
    { id: 1 },
    { id: 2 },
  ]);
  assert.match(calls[1].url, /page=1/);
  assert.equal(calls[0].options.credentials, "include");
  assert.equal(calls[0].options.cache, "no-store");
});
test("fresh load reads persisted server data again", async () => {
  const saved = [{ id: "saved-product", productName: "내 제품" }];
  let requests = 0;
  const request = async () => {
    requests++;
    return { ok: true, json: async () => ({ items: saved, hasNext: false }) };
  };
  assert.deepEqual(await loadOwnedProducts(undefined, request), saved);
  assert.deepEqual(await loadOwnedProducts(undefined, request), saved);
  assert.equal(requests, 2);
});
test("does not present authentication or server failure as an empty list", async () => {
  for (const status of [401, 500])
    await assert.rejects(
      loadOwnedProducts(undefined, async () => ({ ok: false, status })),
      (e) => e.status === status,
    );
});
test("does not guess category without an identifier", () => {
  assert.equal(ownedCategory({}), "미분류");
  assert.equal(ownedCategory({ identifierType: "FOOD_REPORT_NO" }), "식품");
});

import { ownedEditPayload, changeOwnedProduct } from "./items/owned-products.js";
test("catalog edit only sends allowed fields", () => {
  assert.deepEqual(
    ownedEditPayload(
      { registrationType: "CATALOG" },
      { productName: "changed", expiryDate: "2027-01-01", lotNumber: "" },
    ),
    { expiryDate: "2027-01-01", lotNumber: null },
  );
});
test("manual edit clears optional fields and validates name and identifier pair", () => {
  const result = ownedEditPayload(
    { registrationType: "MANUAL" },
    {
      productName: " 물건 ",
      identifierType: "KC_CERT_NO",
      identifierValue: "",
    },
  );
  assert.equal(result.productName, "물건");
  assert.equal(result.identifierType, null);
  assert.equal(result.companyName, null);
  assert.throws(() => ownedEditPayload({}, {}));
  assert.throws(() =>
    ownedEditPayload({}, { productName: "물건", identifierValue: "123" }),
  );
});
test("mutation sends credentials and csrf, handles delete without JSON", async () => {
  const calls = [];
  const request = async (url, options) => {
    calls.push({ url, options });
    return calls.length === 1
      ? {
          ok: true,
          json: async () => ({ headerName: "X-CSRF", token: "test-token" }),
        }
      : { ok: true, status: 204 };
  };
  assert.equal(
    await changeOwnedProduct("id", "DELETE", undefined, request),
    null,
  );
  assert.equal(calls[1].options.method, "DELETE");
  assert.equal(calls[1].options.headers["X-CSRF"], "test-token");
  assert.equal(calls[1].options.credentials, "include");
  assert.equal(calls[1].options.body, undefined);
});
test("failed save is not treated as successful", async () => {
  let n = 0;
  const request = async () =>
    ++n === 1
      ? { ok: true, json: async () => ({ headerName: "X-CSRF", token: "t" }) }
      : {
          ok: false,
          status: 400,
          json: async () => ({ message: "입력 오류" }),
        };
  await assert.rejects(
    changeOwnedProduct("id", "PATCH", { productName: "물건" }, request),
    /입력 오류/,
  );
});

import { ownedRecallLinks } from "./items/owned-products.js";
test("owned recall links use the nested recall identity, not the match wrapper", () => {
  const recall = { id: "real-recall-id", productName: "리콜 제품" };
  assert.deepEqual(
    ownedRecallLinks({ items: [{ recall, matchStatus: "CANDIDATE" }] }),
    [recall],
  );
  assert.deepEqual(ownedRecallLinks({ items: [{}] }), []);
  assert.deepEqual(ownedRecallLinks(undefined), []);
});
