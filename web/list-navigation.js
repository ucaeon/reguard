const sources = ["", "FOOD_I0490", "SAFETY_RECALL"];
const categories = ["", "FOOD", "HEALTH_SUPPLEMENT"];
function dateValue(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return "";
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10) === value
    ? value
    : "";
}
export function readListState(search) {
  const params = new URLSearchParams(search);
  const number = Number(params.get("page") || 1);
  let from = dateValue(params.get("from")),
    to = dateValue(params.get("to"));
  if (from && to && from > to) {
    from = "";
    to = "";
  }
  return {
    term: (params.get("q") || "").slice(0, 100),
    page:
      Number.isSafeInteger(number) && number >= 1 && number <= 100000
        ? number - 1
        : 0,
    source: sources.includes(params.get("source")) ? params.get("source") : "",
    category: categories.includes(params.get("category"))
      ? params.get("category")
      : "",
    from,
    to,
  };
}
export function listUrl({
  view = "recalls",
  term = "",
  page = 0,
  source = "",
  category = "",
  from = "",
  to = "",
}) {
  const params = new URLSearchParams({ view });
  if (term) params.set("q", term);
  if (page > 0) params.set("page", String(page + 1));
  if (view === "recalls") {
    if (source) params.set("source", source);
    if (from) params.set("from", from);
    if (to) params.set("to", to);
  } else if (category) params.set("category", category);
  return `/?${params}`;
}
export function recallReturnUrl(search) {
  const value = new URLSearchParams(search).get("returnTo");
  if (!value) return "/?view=recalls";
  try {
    const base = "https://reguard.invalid";
    const url = new URL(value, base);
    if (
      url.origin !== base ||
      url.pathname !== "/" ||
      url.searchParams.get("view") !== "recalls"
    )
      return "/?view=recalls";
    return listUrl({ ...readListState(url.search), view: "recalls" });
  } catch {
    return "/?view=recalls";
  }
}
export const scrollKey = (url) => `reguard:list-position:v1:${url}`;
export function rememberListPosition(url) {
  if (!url) return;
  try {
    sessionStorage.setItem(scrollKey(url), String(window.scrollY));
  } catch {
    /* Storage may be disabled. URL state still works. */
  }
}
