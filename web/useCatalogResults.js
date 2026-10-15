import { useEffect, useState } from "react";
import { catalogApi } from "./lib/catalog-api.js";
import { catalogPath, catalogPage } from "./lib/catalog-query.js";
export default function useCatalogResults(options) {
  const path = catalogPath(options);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setResult(null);
    setError(null);
    catalogApi(path, { signal: controller.signal }).then(
      (response) => {
        if (!controller.signal.aborted) setResult({ path, response });
      },
      (failure) => {
        if (!controller.signal.aborted)
          setError({ path, message: failure.message });
      },
    );
    return () => controller.abort();
  }, [path, options.retry]);
  const current = result?.path === path ? result.response : null;
  const message = error?.path === path ? error.message : "";
  return {
    data: catalogPage(current, options.view, options.page),
    loading: !!path && !current && !message,
    error: message,
  };
}
