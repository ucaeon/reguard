import React from "react";
import { test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuthPage from "../auth/AuthPage.jsx";
import { navigateTo } from "../lib/navigation.js";
vi.mock("../lib/navigation.js", () => ({ navigateTo: vi.fn() }));
test("login remains on form when session cookie is missing and navigates after confirmation", async () => {
  let authorized = false;
  navigateTo.mockClear();
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, o = {}) => {
    if (url.endsWith("/csrf"))
      return new Response(
        JSON.stringify({ headerName: "X-CSRF", token: "test" }),
      );
    if (url.endsWith("/login")) {
      expect(o.credentials).toBe("include");
      return new Response("{}");
    }
    if (url.endsWith("/me"))
      return new Response("{}", { status: authorized ? 200 : 401 });
    throw new Error(url);
  });
  render(<AuthPage />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("이메일"), "ui-test@example.com");
  await user.type(
    screen.getByLabelText("비밀번호", { exact: true }),
    "Test-password-123",
  );
  await user.click(screen.getByRole("button", { name: "로그인", exact: true }));
  expect(
    await screen.findByText(/로그인 상태를 유지하지 못했어요/),
  ).toBeTruthy();
  expect(navigateTo).not.toHaveBeenCalled();
  authorized = true;
  await user.click(screen.getByRole("button", { name: "로그인", exact: true }));
  await waitFor(() => expect(navigateTo).toHaveBeenCalledWith("/?view=items"));
});
