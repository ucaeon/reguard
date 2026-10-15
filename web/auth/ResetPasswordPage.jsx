import { apiRequest, getCsrf } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import React, { useState } from "react";
import "./auth.css";

export default function ResetPasswordPage() {
  const [token] = useState(() =>
    new URLSearchParams(location.search).get("token"),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setError("");
    if (
      token &&
      (values.password.length < 8 ||
        new TextEncoder().encode(values.password).length > 72)
    ) {
      setError("비밀번호는 8자 이상, 영문 기준 72자 이하로 입력해 주세요.");
      return;
    }
    if (token && values.password !== values.confirm) {
      setError("비밀번호가 일치하지 않아요.");
      return;
    }
    setBusy(true);
    try {
      const csrf = await getCsrf(
        "/api/v1/auth/csrf",
        "서버 연결을 확인해 주세요.",
      );
      const response = await apiRequest(
        `/api/v1/auth/password-reset/${token ? "confirm" : "request"}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            [csrf.headerName]: csrf.token,
          },
          body: JSON.stringify(
            token
              ? { token, newPassword: values.password }
              : { email: values.email.trim() },
          ),
        },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          data.message || "요청을 처리하지 못했어요. 다시 시도해 주세요.",
        );
      }
      if (token) history.replaceState(null, "", "/?view=reset-password");
      setDone(true);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <SiteHeader active="" variant="auth" />
      <main className="auth-main">
        <section className="auth-panel" aria-labelledby="reset-title">
          <h1 id="reset-title">비밀번호 재설정</h1>
          <p className="auth-intro">
            {token
              ? "새 비밀번호를 입력해 주세요."
              : "가입한 이메일로 재설정 링크를 보내드려요."}
          </p>
          {done ? (
            <p className="auth-success" role="status">
              {token
                ? "비밀번호를 변경했어요. 다시 로그인해 주세요."
                : "가입된 이메일이면 재설정 안내를 보냈어요. 메일함을 확인해 주세요."}
            </p>
          ) : (
            <form onSubmit={submit} aria-busy={busy}>
              {token ? (
                <>
                  <div className="auth-field">
                    <label htmlFor="new-password">새 비밀번호</label>
                    <input
                      id="new-password"
                      name="password"
                      type="password"
                      autoComplete="new-password"
                      required
                      disabled={busy}
                    />
                  </div>
                  <div className="auth-field">
                    <label htmlFor="confirm-password">비밀번호 확인</label>
                    <input
                      id="confirm-password"
                      name="confirm"
                      type="password"
                      autoComplete="new-password"
                      required
                      disabled={busy}
                    />
                  </div>
                </>
              ) : (
                <div className="auth-field">
                  <label htmlFor="reset-email">이메일</label>
                  <input
                    id="reset-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    maxLength={320}
                    required
                    disabled={busy}
                  />
                </div>
              )}
              {error && (
                <p className="auth-error" role="alert">
                  {error}
                </p>
              )}
              <button className="auth-submit" disabled={busy}>
                {busy
                  ? "잠시만 기다려 주세요"
                  : token
                    ? "비밀번호 변경"
                    : "재설정 링크 받기"}
              </button>
            </form>
          )}
          <p className="auth-switch">
            <a href="/?view=login">로그인</a>
            {token && <a href="/?view=reset-password">링크 다시 받기</a>}
          </p>
        </section>
      </main>
      <footer className="auth-footer">
        © {new Date().getFullYear()} ReGuard
      </footer>
    </div>
  );
}
