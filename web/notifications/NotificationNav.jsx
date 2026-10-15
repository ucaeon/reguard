import { apiRequest } from "../lib/api-client.js";
import React, { useEffect, useState } from "react";
import "./notification-nav.css";
export default function NotificationNav() {
  const [count, setCount] = useState(0),
    [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let revision = 0;
    async function refresh() {
      const version = ++revision;
      try {
        const r = await apiRequest("/api/v1/me/notifications/unread-count", {
          credentials: "include",
          cache: "no-store",
          signal: controller.signal,
        });
        if (r.ok) {
          const data = await r.json();
          if (version === revision) {
            setCount(data.count);
            setUnavailable(false);
          }
        } else if (version === revision) {
          if (r.status === 401) {
            setCount(0);
            setUnavailable(false);
          } else setUnavailable(true);
        }
      } catch (e) {
        if (e.name !== "AbortError" && version === revision)
          setUnavailable(true);
      }
    }
    function read() {
      ++revision;
      setCount((n) => Math.max(0, n - 1));
      refresh();
      channel?.postMessage("read");
    }
    function visible() {
      if (document.visibilityState === "visible") refresh();
    }
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("reguard-notifications");
    if (channel) channel.onmessage = refresh;
    refresh();
    const timer = setInterval(visible, 30000);
    window.addEventListener("reguard-notification-read", read);
    window.addEventListener("focus", visible);
    document.addEventListener("visibilitychange", visible);
    return () => {
      ++revision;
      controller.abort();
      clearInterval(timer);
      channel?.close();
      window.removeEventListener("reguard-notification-read", read);
      window.removeEventListener("focus", visible);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);
  return (
    <a
      title={
        unavailable
          ? "알림 개수를 확인하지 못했어요. 알림 페이지에서 다시 확인해 주세요."
          : undefined
      }
      className="notification-nav"
      href="/?view=notifications"
      aria-current={
        new URLSearchParams(location.search).get("view") === "notifications"
          ? "page"
          : undefined
      }
    >
      알림
      {count > 0 && (
        <span
          className="notification-nav-badge"
          aria-label={`안 읽은 알림 ${count}개`}
        >
          {count > 99 ? "99+" : count}
        </span>
      )}
    </a>
  );
}
