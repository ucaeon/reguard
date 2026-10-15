export const PAGE_SIZE = 12;
export const RECALL_PAGE_GROUP = 3;
export function catalogPath({
  view,
  term,
  page,
  category,
  recallSource,
  recallFilters,
}) {
  if (!["search", "recalls"].includes(view) || (view === "search" && !term))
    return null;
  const recalls = view === "recalls";
  return (
    (recalls ? "/recalls?" : "/products?") +
    new URLSearchParams({
      ...(term ? { q: term } : {}),
      page: recalls ? Math.floor(page / RECALL_PAGE_GROUP) : page,
      size: recalls ? PAGE_SIZE * RECALL_PAGE_GROUP : PAGE_SIZE,
      ...(!recalls && category ? { category } : {}),
      ...(recalls && recallSource ? { source: recallSource } : {}),
      ...(recalls
        ? {
            sort: recallFilters.sort,
            ...(recallFilters.from ? { from: recallFilters.from } : {}),
            ...(recallFilters.to ? { to: recallFilters.to } : {}),
          }
        : {}),
    })
  );
}
export function catalogPage(response, view, page) {
  if (!response || view !== "recalls") return response;
  const offset = (page % RECALL_PAGE_GROUP) * PAGE_SIZE;
  return {
    ...response,
    items: response.items.slice(offset, offset + PAGE_SIZE),
    hasNext: offset + PAGE_SIZE < response.items.length || response.hasNext,
    hasNextGroup: response.hasNext,
    pageNumbers: Array.from(
      { length: Math.ceil(response.items.length / PAGE_SIZE) },
      (_, i) => Math.floor(page / RECALL_PAGE_GROUP) * RECALL_PAGE_GROUP + i,
    ),
  };
}
