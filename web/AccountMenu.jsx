import { navigateTo } from "./lib/navigation.js";
import { useProfile } from "./auth/ProfileProvider.jsx";
import { apiRequest, getCsrf } from "./lib/api-client.js";
import React, { useEffect, useRef, useState, useId } from "react";
import "./account-menu.css";
export default function AccountMenu() {
  const { profile, loading, error: profileError } = useProfile();
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const root = useRef(null),
    trigger = useRef(null),
    id = useId();
  useEffect(() => {
    if (!open) return;
    function outside(e) {
      if (!root.current?.contains(e.target)) setOpen(false);
    }
    function escape(e) {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  async function logout() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const csrf = await getCsrf("/api/v1/auth/csrf", undefined);
      const result = await apiRequest("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
        headers: { [csrf.headerName]: csrf.token },
      });
      if (!result.ok && result.status !== 401) throw Error();
      navigateTo("/");
    } catch {
      setError("로그아웃하지 못했어요. 다시 시도해 주세요.");
      setBusy(false);
    }
  }
  if (loading)
    return <span className="account-loading" aria-label="계정 확인 중" />;
  if (!profile && profileError)
    return (
      <a className="account-login" href="/?view=settings" role="status">
        계정 확인 필요
      </a>
    );
  if (!profile)
    return (
      <a className="account-login" href="/?view=login">
        로그인
      </a>
    );
  return (
    <div
      className="account-menu"
      ref={root}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <button
        title={profileError ? "계정 정보를 새로 불러오지 못했어요." : undefined}
        className="account-trigger"
        ref={trigger}
        aria-label={`${profile.displayName} 계정 메뉴`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        {profile.photo ? (
          <img src={profile.photo} alt="프로필 사진" />
        ) : (
          <span className="account-avatar" aria-hidden="true">
            {profile.displayName?.slice(0, 1) || "R"}
          </span>
        )}
        <span className="account-name">{profile.displayName}</span>
        <span aria-hidden="true" className="account-chevron">
          ⌄
        </span>
      </button>
      {open && (
        <div className="account-dropdown" id={id}>
          <a href="/?view=settings">내 정보 수정</a>
          <button onClick={logout} disabled={busy}>
            {busy ? "로그아웃 중…" : "로그아웃"}
          </button>
          {error && <p role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}
