import { test, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import useCatalogResults from "../useCatalogResults.js";
test("same page group avoids refetch and obsolete requests are aborted", async () => {
  const calls = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    calls.push({ url, signal: options.signal });
    return new Response(
      JSON.stringify({
        items: Array.from({ length: 36 }, (_, id) => ({ id })),
        hasNext: true,
      }),
    );
  });
  const base = {
    view: "recalls",
    term: "",
    page: 0,
    recallFilters: { sort: "latest" },
    retry: 0,
  };
  const { result, rerender, unmount } = renderHook(
    (props) => useCatalogResults(props),
    { initialProps: base },
  );
  await waitFor(() => expect(result.current.data?.items[0].id).toBe(0));
  rerender({ ...base, page: 2 });
  expect(result.current.data.items[0].id).toBe(24);
  expect(calls.length).toBe(1);
  rerender({ ...base, page: 3 });
  await waitFor(() => expect(calls.length).toBe(2));
  expect(calls[0].signal.aborted).toBe(true);
  unmount();
  expect(calls[1].signal.aborted).toBe(true);
});
test("late response from a previous search never replaces the current result", async () => {
  let finishOld;
  vi.spyOn(globalThis, "fetch").mockImplementation((url) =>
    url.includes("q=old")
      ? new Promise((resolve) => (finishOld = resolve))
      : Promise.resolve(
          new Response(
            JSON.stringify({ items: [{ id: "new" }], hasNext: false }),
          ),
        ),
  );
  const base = {
    view: "search",
    term: "old",
    page: 0,
    recallFilters: { sort: "latest" },
    retry: 0,
  };
  const { result, rerender } = renderHook((props) => useCatalogResults(props), {
    initialProps: base,
  });
  rerender({ ...base, term: "new" });
  await waitFor(() => expect(result.current.data?.items[0].id).toBe("new"));
  finishOld(
    new Response(JSON.stringify({ items: [{ id: "old" }], hasNext: false })),
  );
  await waitFor(() => expect(result.current.data.items[0].id).toBe("new"));
});
