import { navigateTo } from "../lib/navigation.js";
import { apiRequest, getCsrf } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import { conciseRecallReason } from "../recalls/recall-reason.js";
import { recallName } from "../format.js";
import React, { useEffect, useState, useRef } from "react";
import "./notifications.css";
export default function NotificationsPage() {
  const [items, setItems] = useState([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [unauthorized, setUnauthorized] = useState(false),
    [unreadOnly, setUnreadOnly] = useState(false),
    [retry, setRetry] = useState(0),
    [busy, setBusy] = useState(null),
    [actionError, setActionError] = useState("");
  const lock = useRef(false);
  const [details, setDetails] = useState({});
  useEffect(() => {
    const controller = new AbortController();
    const queue = [...new Set(items.map((x) => x.recallId))];
    async function worker() {
      while (queue.length) {
        const id = queue.shift();
        try {
          const r = await apiRequest(
            "/api/v1/recalls/" + encodeURIComponent(id),
            { signal: controller.signal },
          );
          if (r.ok) {
            const data = await r.json();
            setDetails((old) => ({ ...old, [id]: data }));
          }
        } catch {}
      }
    }
    Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker));
    return () => controller.abort();
  }, [items.map((x) => x.recallId).join(",")]);
  function name(item) {
    const fromMessage =
      item.message?.split("에 관련된 리콜 정보가 있습니다.")[0];
    return item.message?.includes("에 관련된 리콜 정보가 있습니다.")
      ? fromMessage
      : details[item.recallId]
        ? recallName(details[item.recallId])
        : "등록한 물건";
  }

  useEffect(() => {
    const controller = new AbortController();
    let fetching = false;
    async function load() {
      if (fetching) return;
      fetching = true;
      try {
        const rows = [];
        for (let page = 0; ; page++) {
          const response = await apiRequest(
            `/api/v1/me/notifications?page=${page}&size=100`,
            {
              credentials: "include",
              cache: "no-store",
              signal: controller.signal,
            },
          );
          if (!response.ok) {
            const e = new Error(
              response.status === 401
                ? "로그인하고 내 물건의 알림을 확인하세요."
                : "알림을 불러오지 못했어요.",
            );
            e.status = response.status;
            throw e;
          }
          const data = await response.json();
          rows.push(...data.items);
          if (!data.hasNext) break;
        }
        if (!lock.current) setItems(rows);
        setUnauthorized(false);
        setError("");
      } catch (e) {
        if (e.name !== "AbortError") {
          setUnauthorized(e.status === 401);
          setError(e.message);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
        fetching = false;
      }
    }
    load();
    const refresh = () => {
      if (document.visibilityState === "visible") load();
    };
    const timer = setInterval(refresh, 60000);
    window.addEventListener("focus", refresh);
    return () => {
      controller.abort();
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [retry]);
  async function open(item) {
    if (lock.current) return;
    lock.current = true;
    setBusy(item.id);
    setActionError("");
    try {
      if (!item.readAt) {
        const csrf = await getCsrf(
          "/api/v1/me/notifications/csrf",
          "읽음 처리에 실패했어요. 다시 시도해 주세요.",
        );
        const response = await apiRequest(
          `/api/v1/me/notifications/${encodeURIComponent(item.id)}/read`,
          {
            method: "PATCH",
            credentials: "include",
            headers: { [csrf.headerName]: csrf.token },
          },
        );
        if (!response.ok)
          throw new Error(
            response.status === 401
              ? "로그인이 만료됐어요. 다시 로그인해 주세요."
              : "읽음 처리에 실패했어요. 다시 시도해 주세요.",
          );
        const updated = await response.json();
        window.dispatchEvent(new Event("reguard-notification-read"));
        setItems((old) => old.map((x) => (x.id === item.id ? updated : x)));
      }
      navigateTo(
        `/?view=recall&id=${encodeURIComponent(item.recallId)}&from=notifications`,
      );
    } catch (e) {
      setActionError(e.message);
    } finally {
      lock.current = false;
      setBusy(null);
    }
  }
  const unread = items.filter((x) => !x.readAt).length,
    shown = unreadOnly ? items.filter((x) => !x.readAt) : items;
  return (
    <div className="about-page">
      <SiteHeader active="notifications" variant="about" />
      <main className="nt-main">
        <h1>알림</h1>
        <p className="nt-lead">내 물건과 관련된 리콜 소식을 확인하세요.</p>
        <div className="nt-tabs">
          <button
            aria-pressed={!unreadOnly}
            className={!unreadOnly ? "active" : ""}
            onClick={() => setUnreadOnly(false)}
          >
            전체
          </button>
          <button
            aria-pressed={unreadOnly}
            className={unreadOnly ? "active" : ""}
            onClick={() => setUnreadOnly(true)}
          >
            안 읽음{!error && !loading && unread > 0 && <span>{unread}</span>}
          </button>
        </div>
        {actionError && (
          <p role="alert" className="nt-error">
            {actionError}
          </p>
        )}
        {loading ? (
          <p className="nt-empty" role="status">
            알림을 불러오고 있어요…
          </p>
        ) : error ? (
          <div className="nt-empty" role="alert">
            <h2>{error}</h2>
            {unauthorized ? (
              <a href="/?view=login">로그인</a>
            ) : (
              <button onClick={() => setRetry((x) => x + 1)}>다시 시도</button>
            )}
          </div>
        ) : !shown.length ? (
          <div className="nt-empty">
            <svg
              width="64"
              height="64"
              viewBox="0 0 64 64"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M16 43V28a16 16 0 0 1 32 0v15l5 7H11l5-7Z"
                fill="#eef5f4"
                stroke="#a0bcb8"
                strokeWidth="2"
              />
              <path
                d="M26 56a7 7 0 0 0 12 0"
                stroke="#0f766e"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            <h2>
              {unreadOnly
                ? "새 알림을 모두 확인했어요"
                : "아직 도착한 알림이 없어요"}
            </h2>
            <p>
              {unreadOnly
                ? "새로운 소식이 생기면 여기서 확인하세요."
                : "등록한 물건과 관련된 리콜이 발견되면 알려드려요."}
            </p>
            <a href="/?view=items">내 물건 보기 →</a>
          </div>
        ) : (
          <div className="nt-list">
            {shown.map((item) => (
              <article
                className={`nt-row ${item.readAt ? "" : "unread"}`}
                key={item.id}
              >
                <span
                  className="nt-indicator"
                  aria-label={item.readAt ? "읽음" : "안 읽음"}
                />
                <div className="nt-content">
                  <strong>
                    {/^\[(예시|테스트)\]/.test(item.title) ? "[예시] " : ""}내
                    물건 ‘{name(item)}’에 대한 리콜 알림이 왔어요.
                  </strong>
                  <span className="nt-message">
                    {details[item.recallId]?.reason
                      ? conciseRecallReason(
                          details[item.recallId].reason,
                        ).replace(/\n/g, " · ")
                      : "리콜 이유를 상세페이지에서 확인해 주세요."}
                  </span>
                  <time className="nt-date" dateTime={item.createdAt}>
                    {new Date(item.createdAt).toLocaleDateString("ko-KR")}
                  </time>
                </div>
                <a
                  className="nt-detail"
                  href={`/?view=recall&id=${encodeURIComponent(item.recallId)}&from=notifications`}
                  aria-label={`${name(item)} 리콜 상세보기`}
                  aria-disabled={busy !== null}
                  onClick={(e) => {
                    e.preventDefault();
                    open(item);
                  }}
                >
                  {busy === item.id ? "처리 중…" : "상세보기"}{" "}
                  <span aria-hidden="true">→</span>
                </a>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
