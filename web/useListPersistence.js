import { useEffect, useLayoutEffect, useRef } from "react";
import { rememberListPosition, scrollKey } from "./list-navigation.js";

export default function useListPersistence(url, ready) {
  const pending = useRef(undefined);
  const currentUrl = useRef(url);
  if (pending.current === undefined) {
    let top = 0;
    try {
      top = Number(sessionStorage.getItem(scrollKey(url))) || 0;
    } catch {
      /* URL state remains available. */
    }
    pending.current = Number.isFinite(top) && top >= 0 ? top : 0;
  }
  if (currentUrl.current !== url) {
    currentUrl.current = url;
    pending.current = 0;
  }
  useEffect(() => {
    if (!url) return;
    if (location.pathname + location.search !== url)
      history.pushState(null, "", url);
  }, [url]);
  useEffect(() => {
    if (!url) return;
    const previous = history.scrollRestoration;
    history.scrollRestoration = "manual";
    const save = () => {
      if (ready && pending.current === null) rememberListPosition(url);
    };
    window.addEventListener("pagehide", save);
    return () => {
      window.removeEventListener("pagehide", save);
      history.scrollRestoration = previous;
    };
  }, [url, ready]);
  // Restore only once results have rendered, rather than while the page is a short loading screen.
  useLayoutEffect(() => {
    if (!url || !ready || pending.current === null) return;
    const top = pending.current;
    const frame = requestAnimationFrame(() => {
      window.scrollTo({ top, behavior: "instant" });
      pending.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [url, ready]);
}
