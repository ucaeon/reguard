import test from "node:test";
import assert from "node:assert/strict";
import { apiRequest, getCsrf } from "./lib/api-client.js";

test("transport preserves body, abort signal and HTTP status with cookie defaults", async () => {
  const controller = new AbortController();
  const response = await apiRequest(
    "/api/v1/me/products",
    { method: "POST", body: "{}", signal: controller.signal },
    async (url, options) => {
      assert.equal(options.credentials, "include");
      assert.equal(options.cache, "no-store");
      assert.equal(options.method, "POST");
      assert.equal(options.body, "{}");
      assert.equal(options.signal, controller.signal);
      return new Response(null, { status: 401 });
    },
  );
  assert.equal(response.status, 401);
});
test("credentials cannot accidentally be sent to an external URL", () => {
  assert.throws(() => apiRequest("https://example.com/api/v1/me"));
});
test("CSRF tokens remain isolated by service and are refreshed every time", async () => {
  const paths = [];
  const request = async (path) => {
    paths.push(path);
    return new Response(
      JSON.stringify({ headerName: "X-CSRF", token: String(paths.length) }),
    );
  };
  assert.equal(
    (await getCsrf("/api/v1/auth/csrf", undefined, request)).token,
    "1",
  );
  assert.equal(
    (await getCsrf("/api/v1/me/notifications/csrf", undefined, request)).token,
    "2",
  );
  assert.equal(
    (await getCsrf("/api/v1/auth/csrf", undefined, request)).token,
    "3",
  );
  assert.equal(paths.length, 3);
});
test("token failures, malformed tokens and cancellation remain failures", async () => {
  await assert.rejects(
    getCsrf(
      undefined,
      "연결 오류",
      async () => new Response(null, { status: 503 }),
    ),
    (e) => e.status === 503 && e.message === "연결 오류",
  );
  await assert.rejects(
    getCsrf(undefined, undefined, async () => new Response("{}")),
  );
  await assert.rejects(
    apiRequest("/api/v1/me", {}, async () => {
      throw new DOMException("cancel", "AbortError");
    }),
    (e) => e.name === "AbortError",
  );
});
