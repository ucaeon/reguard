import React from "react";
import { test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NotificationsPage from "../notifications/NotificationsPage.jsx";
import { navigateTo } from "../lib/navigation.js";
vi.mock("../lib/navigation.js", () => ({ navigateTo: vi.fn() }));
test("read confirmation reduces unread badge before opening recall detail", async () => {
  let read = false;
  navigateTo.mockClear();
  const item = {
    id: "notice",
    recallId: "recall",
    title: "리콜",
    message: "테스트 물건에 관련된 리콜 정보가 있습니다.",
    createdAt: "2026-10-15T00:00:00Z",
    readAt: null,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, o = {}) => {
    let data;
    if (url.endsWith("unread-count")) data = { count: read ? 0 : 1 };
    else if (url.endsWith("/csrf"))
      data = { headerName: "X-CSRF", token: "test" };
    else if (url.endsWith("/read")) {
      expect(o.method).toBe("PATCH");
      expect(o.headers["X-CSRF"]).toBe("test");
      read = true;
      data = { ...item, readAt: "2026-10-15T01:00:00Z" };
    } else if (url.startsWith("/api/v1/me/notifications?"))
      data = { items: [item], hasNext: false };
    else if (url === "/api/v1/recalls/recall")
      data = {
        id: "recall",
        productName: "테스트 물건",
        reason: "세균수 기준 규격 부적합",
      };
    else throw new Error("Unexpected request: " + url);
    return new Response(JSON.stringify(data));
  });
  render(<NotificationsPage />);
  expect(await screen.findByLabelText("안 읽은 알림 1개")).toBeTruthy();
  await userEvent
    .setup()
    .click(
      await screen.findByRole("link", { name: "테스트 물건 리콜 상세보기" }),
    );
  await waitFor(() =>
    expect(navigateTo).toHaveBeenCalledWith(
      "/?view=recall&id=recall&from=notifications",
    ),
  );
  await waitFor(() =>
    expect(screen.queryByLabelText("안 읽은 알림 1개")).toBeNull(),
  );
});
