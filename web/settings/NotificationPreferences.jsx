import { apiRequest, getCsrf } from "../lib/api-client.js";
import React, { useEffect, useState, useRef } from "react";
export default function NotificationPreferences() {
  const [enabled, setEnabled] = useState(true),
    [loaded, setLoaded] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [retry, setRetry] = useState(0);
  const lock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    apiRequest("/api/v1/me/notification-preferences", {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw Error("알림 설정을 불러오지 못했어요.");
        return r.json();
      })
      .then((data) => {
        setEnabled(data.enabled);
        setLoaded(true);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [retry]);
  async function save(e) {
    e.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const csrf = await getCsrf("/api/v1/auth/csrf", undefined);
      const response = await apiRequest("/api/v1/me/notification-preferences", {
        method: "PUT",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          [csrf.headerName]: csrf.token,
        },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw Error();
      const data = await response.json();
      setEnabled(data.enabled);
      setNotice("알림 설정을 저장했어요.");
    } catch {
      setError("저장하지 못했어요. 다시 시도해 주세요.");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <section>
      <h2>알림 설정</h2>
      {loaded ? (
        <form onSubmit={save}>
          <div className="settings-notification-row">
            <div>
              <strong id="recall-alert-label">내 물건 리콜 알림</strong>
              <p id="recall-alert-help">
                끄면 새 알림을 받지 않아요. 기존 알림은 유지돼요.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-labelledby="recall-alert-label"
              aria-describedby="recall-alert-help"
              className="settings-switch"
              disabled={busy}
              onClick={() => {
                setEnabled(!enabled);
                setNotice("");
              }}
            >
              <span />
            </button>
          </div>
          <div className="settings-save-row">
            <button className="settings-save" disabled={busy}>
              {busy ? "저장 중…" : "알림 설정 저장"}
            </button>
          </div>
        </form>
      ) : !error ? (
        <p role="status">알림 설정을 불러오고 있어요…</p>
      ) : (
        <button onClick={() => setRetry((x) => x + 1)}>다시 시도</button>
      )}
      {error && (
        <p role="alert" className="settings-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="settings-notice">
          {notice}
        </p>
      )}
    </section>
  );
}
