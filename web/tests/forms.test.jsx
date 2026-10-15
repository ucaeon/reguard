import React from "react";
import { test, expect, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ManualRegistration from "../items/ManualRegistration.jsx";
import OwnedProductDialog from "../items/OwnedProductDialog.jsx";
import SettingsPage from "../settings/SettingsPage.jsx";
import ProfileProvider from "../auth/ProfileProvider.jsx";
import { profileStore } from "../lib/profile-store.js";
const json = (data, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(data), { status });
function mockApi(handle) {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (url, options = {}) => {
      if (url.endsWith("/csrf"))
        return json({ headerName: "X-CSRF", token: "test" });
      if (url.endsWith("/unread-count")) return json({ count: 0 });
      if (url.endsWith("/notification-preferences"))
        return json({ enabled: true });
      return handle(url, options);
    },
  );
}
test("manual registration submits entered data and shows saved product", async () => {
  let saved;
  mockApi((url, o) => {
    expect(url).toBe("/api/v1/me/products");
    saved = JSON.parse(o.body);
    return json({ id: "test", ...saved }, 201);
  });
  render(<ManualRegistration />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/제품명/), "테스트 식품");
  await user.click(screen.getByRole("button", { name: "내 물건에 등록" }));
  expect(
    await screen.findByRole("heading", { name: "물건을 등록했어요" }),
  ).toBeTruthy();
  expect(saved.productName).toBe("테스트 식품");
  expect(saved.registrationType).toBe("MANUAL");
});
test("edit failure preserves input, retry saves, delete handles empty response", async () => {
  let fail = true;
  const calls = [];
  const success = vi.fn();
  mockApi((url, o) => {
    calls.push(o);
    return fail
      ? json({ message: "잠시 후 다시 시도" }, 503)
      : json(null, o.method === "DELETE" ? 204 : 200);
  });
  const item = {
    id: "owned-1",
    registrationType: "MANUAL",
    productName: "기존 이름",
  };
  const view = render(
    <OwnedProductDialog
      item={item}
      mode="edit"
      onClose={() => {}}
      onSuccess={success}
    />,
  );
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText("제품명"));
  await user.type(screen.getByLabelText("제품명"), "수정 이름");
  await user.click(screen.getByRole("button", { name: "저장" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByLabelText("제품명").value).toBe("수정 이름");
  fail = false;
  await user.click(screen.getByRole("button", { name: "저장" }));
  await waitFor(() => expect(success).toHaveBeenCalledOnce());
  expect(JSON.parse(calls.at(-1).body).productName).toBe("수정 이름");
  view.unmount();
  render(
    <OwnedProductDialog
      item={item}
      mode="delete"
      onClose={() => {}}
      onSuccess={success}
    />,
  );
  await user.click(screen.getByRole("button", { name: "삭제" }));
  await waitFor(() => expect(success).toHaveBeenCalledTimes(2));
  expect(calls.at(-1).method).toBe("DELETE");
});
test("header and settings share profile fetch; focus refresh preserves unsaved nickname", async () => {
  const profile = {
    id: "user-1",
    displayName: "기존 닉네임",
    photo: null,
    email: "test@example.com",
  };
  let reads = 0;
  profileStore.update(null);
  mockApi((url, o) => {
    expect(url).toBe("/api/v1/me/profile");
    if (o.method === "PUT") return json({ ...profile, ...JSON.parse(o.body) });
    reads++;
    return json({ ...profile });
  });
  render(
    <ProfileProvider>
      <SettingsPage />
    </ProfileProvider>,
  );
  const input = await screen.findByLabelText("닉네임");
  expect(reads).toBe(1);
  const user = userEvent.setup();
  await user.clear(input);
  await user.type(input, "새 닉네임");
  await act(async () => {
    await profileStore.refresh();
  });
  expect(input.value).toBe("새 닉네임");
  await user.click(screen.getByRole("button", { name: "저장" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "새 닉네임 계정 메뉴" }),
    ).toBeTruthy(),
  );
});
