import test from "node:test";
import assert from "node:assert/strict";
import { createProfileStore } from "./lib/profile-store.js";
test("concurrent subscribers share one profile request", async () => {
  let count = 0,
    finish;
  const store = createProfileStore(() => {
    count++;
    return new Promise((r) => (finish = r));
  });
  const a = store.refresh(),
    b = store.refresh();
  await Promise.resolve();
  assert.equal(count, 1);
  finish({ id: "a" });
  await Promise.all([a, b]);
  assert.equal(store.getSnapshot().profile.id, "a");
});
test("late profile response cannot overwrite a saved profile", async () => {
  let finish;
  const store = createProfileStore(() => new Promise((r) => (finish = r)));
  const request = store.refresh();
  await Promise.resolve();
  store.update({ id: "a", displayName: "new" });
  finish({ id: "a", displayName: "old" });
  await request;
  assert.equal(store.getSnapshot().profile.displayName, "new");
});
test("401 clears identity while temporary failure is visible", async () => {
  let status = 503;
  const store = createProfileStore(async () => {
    throw Object.assign(new Error("unavailable"), { status });
  });
  store.update({ id: "a" });
  await store.refresh();
  assert.equal(store.getSnapshot().profile.id, "a");
  assert.equal(store.getSnapshot().error.status, 503);
  status = 401;
  await store.refresh();
  assert.equal(store.getSnapshot().profile, null);
  assert.equal(store.getSnapshot().error, null);
});
