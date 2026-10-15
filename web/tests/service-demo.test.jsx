import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import ServiceDemo from "../landing/ServiceDemo.jsx";
import { captures, scenes } from "../landing/service-demo-scenes.js";
let intersection;
let reduce = false;
beforeEach(() => {
  vi.useFakeTimers();
  reduce = false;
  vi.stubGlobal("matchMedia", (query) => ({
    matches: reduce && query.includes("reduced-motion"),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback) {
        intersection = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
const advance = () => act(() => vi.advanceTimersByTime(5000));
const visibility = (value) =>
  act(() => intersection([{ isIntersecting: value }]));
test("alerts keep only the inbox without a pointer and respect pause and visibility", () => {
  const { container } = render(<ServiceDemo scene="alerts" label="알림" />);
  expect(container.querySelector("image")).toBeNull();
  visibility(true);
  advance();
  advance();
  advance();
  expect(container.querySelectorAll("image")).toHaveLength(1);
  expect(container.querySelector("image").getAttribute("href")).toBe(
    "/images/service-demo/alerts.jpg",
  );
  expect(container.querySelector(".service-demo-pointer")).toBeNull();
  expect(
    container.querySelector(".service-demo").classList.contains("is-playing"),
  ).toBe(true);
  visibility(false);
  expect(
    container.querySelector(".service-demo").classList.contains("is-playing"),
  ).toBe(false);
  visibility(true);
  fireEvent.click(screen.getByRole("button", { name: "알림 모션 멈춤" }));
  expect(
    container.querySelector(".service-demo").classList.contains("is-playing"),
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "알림 모션 재생" }));
  expect(
    container.querySelector(".service-demo").classList.contains("is-playing"),
  ).toBe(true);
});
test.each(["search", "product", "registered"])(
  "%s plays only its own workflow and restarts on re-entry",
  (scene) => {
    const { container, rerender } = render(
      <ServiceDemo scene={scene} label="등록 단계" />,
    );
    visibility(true);
    for (const name of scenes[scene]) {
      const capture = captures[name];
      expect(
        container.querySelector(".is-current image").getAttribute("href"),
      ).toBe(`/images/service-demo/${capture.file || name}.jpg`);
      act(() => vi.advanceTimersByTime(capture.duration || 5000));
    }
    expect(
      container.querySelector(".is-current image").getAttribute("href"),
    ).toBe(`/images/service-demo/${captures[scenes[scene][0]].file}.jpg`);
    act(() => vi.advanceTimersByTime(captures[scenes[scene][0]].duration));
    rerender(<ServiceDemo scene={scene} label="등록 단계" active={false} />);
    expect(
      container.querySelector(".is-current image").getAttribute("href"),
    ).toBe(`/images/service-demo/${captures[scenes[scene][0]].file}.jpg`);
  },
);
test("reduced motion keeps the selected registration screen without playback", () => {
  reduce = true;
  const { container } = render(
    <ServiceDemo scene="registered" label="등록 완료" />,
  );
  visibility(true);
  advance();
  expect(container.querySelector("image").getAttribute("href")).toContain(
    "manual-empty.jpg",
  );
  expect(
    screen.queryByRole("button", { name: "등록 완료 모션 멈춤" }),
  ).toBeNull();
});
test("inactive registration scenes do not play and missing captures show a fallback", () => {
  const { container } = render(
    <ServiceDemo scene="product" label="제품 정보" active={false} />,
  );
  visibility(true);
  advance();
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain(
    "검색 결과",
  );
  fireEvent.error(container.querySelector("image"));
  expect(screen.getByText(/화면을 불러오지 못했어요/)).toBeTruthy();
});

test("recall plays list to scrolling detail as one flow without scene selectors", () => {
  const { container } = render(<ServiceDemo scene="recall" label="리콜" />);
  visibility(true);
  expect(screen.queryByRole("group", { name: "리콜 장면 선택" })).toBeNull();
  expect(container.querySelector(".is-current image").getAttribute("href")).toContain("recall-list.jpg");
  act(() => vi.advanceTimersByTime(captures["recall-list"].duration));
  expect(container.querySelector(".is-current .service-demo-scroll image").getAttribute("href")).toContain("recall-flow.jpg");
  fireEvent.click(screen.getByRole("button", { name: "리콜 모션 멈춤" }));
  act(() => vi.advanceTimersByTime(captures["recall-flow"].duration));
  expect(container.querySelector(".is-current image").getAttribute("href")).toContain("recall-flow.jpg");
  fireEvent.click(screen.getByRole("button", { name: "리콜 모션 재생" }));
  act(() => vi.advanceTimersByTime(captures["recall-flow"].duration));
  expect(container.querySelector(".is-current image").getAttribute("href")).toContain("recall-list.jpg");
});

test("scrolling back into a paused scene restarts automatic playback", () => {
  const { container } = render(<ServiceDemo scene="search" label="검색" />);
  visibility(true);
  act(() => vi.advanceTimersByTime(captures["search-empty"].duration));
  fireEvent.click(screen.getByRole("button", { name: "검색 모션 멈춤" }));
  visibility(false);
  visibility(true);
  expect(container.querySelector(".service-demo").classList.contains("is-playing")).toBe(true);
  expect(container.querySelector(".is-current image").getAttribute("href")).toContain("search-empty.jpg");
  act(() => vi.advanceTimersByTime(captures["search-empty"].duration));
  expect(container.querySelector(".is-current image").getAttribute("href")).toContain("search-type-1.jpg");
});
