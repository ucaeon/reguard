import { navigateTo } from "../lib/navigation.js";
import { apiRequest, getCsrf } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import React, { useState } from "react";
import "./auth.css";

export default function AuthPage({ signup = false }) {
  const [stage, setStage] = useState("email");
  const [email, setEmail] = useState("");
  const [proof, setProof] = useState("");
  const [mailNotice, setMailNotice] = useState("");
  async function verifyEmail(event, resend = false) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget.form || event.currentTarget;
    const code = new FormData(form).get("code");
    setBusy(true);
    setError("");
    setMailNotice("");
    try {
      const csrf = await getCsrf(
        "/api/v1/auth/csrf",
        "서버 연결을 확인해 주세요.",
      );
      const confirming = stage === "code" && !resend;
      const response = await apiRequest(
        `/api/v1/auth/signup/email/${confirming ? "verify" : "request"}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            [csrf.headerName]: csrf.token,
          },
          body: JSON.stringify({
            email: email.trim(),
            ...(confirming ? { code } : {}),
          }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          data.message ||
            "인증 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
        );
      if (confirming) {
        if (!data.verificationToken)
          throw new Error("인증을 완료하지 못했어요. 다시 시도해 주세요.");
        setProof(data.verificationToken);
        setStage("password");
      } else {
        setStage("code");
        setMailNotice("인증번호를 보냈어요. 10분 안에 입력해 주세요.");
      }
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const invalid = {};
    if (signup && !values.displayName.trim())
      invalid.displayName = "이름을 입력해 주세요.";
    if (
      values.password.length < 8 ||
      new TextEncoder().encode(values.password).length > 72
    ) {
      invalid.password =
        "비밀번호는 8자 이상, 영문 기준 72자 이하로 입력해 주세요.";
    }
    if (signup && values.password !== values.confirm)
      invalid.confirm = "비밀번호가 일치하지 않아요.";
    setErrors(invalid);
    setError("");
    if (Object.keys(invalid).length) {
      event.currentTarget.elements[Object.keys(invalid)[0]].focus();
      return;
    }
    setBusy(true);
    try {
      const csrf = await getCsrf(
        "/api/v1/auth/csrf",
        "지금은 연결이 원활하지 않아요. 잠시 후 다시 시도해 주세요.",
      );
      const body = {
        email: signup ? email.trim() : values.email.trim(),
        password: values.password,
      };
      if (signup) {
        body.displayName = values.displayName.trim();
        body.email = email.trim();
        body.verificationToken = proof;
      }
      const response = await apiRequest(
        `/api/v1/auth/${signup ? "signup" : "login"}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            [csrf.headerName]: csrf.token,
          },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) {
        throw new Error(
          response.status === 409
            ? "이미 가입된 이메일이에요. 로그인해 주세요."
            : response.status === 401
              ? "이메일 또는 비밀번호를 확인해 주세요."
              : response.status === 400
                ? "입력한 정보를 다시 확인해 주세요."
                : "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
        );
      }
      if (!signup) {
        const session = await apiRequest("/api/v1/me", {
          credentials: "include",
          cache: "no-store",
        });
        if (!session.ok)
          throw new Error(
            "로그인 상태를 유지하지 못했어요. 쿠키 허용 여부를 확인하고 다시 시도해 주세요.",
          );
      }
      navigateTo(signup ? "/?view=login&joined=1" : "/?view=items");
    } catch (failure) {
      setError(
        failure instanceof TypeError
          ? "서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요."
          : failure.message,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <SiteHeader active="" variant="auth" />
      <main className="auth-main">
        <section className="auth-panel" aria-labelledby="auth-title">
          <h1 id="auth-title">{signup ? "회원가입" : "로그인"}</h1>
          <p className="auth-intro">
            {signup
              ? stage === "password"
                ? "이메일 인증이 완료됐어요. 이름과 비밀번호를 입력해 주세요."
                : stage === "code"
                  ? "이메일로 보낸 인증번호를 입력해 주세요."
                  : "가입할 이메일을 먼저 인증해 주세요."
              : "로그인하고 내 물건의 소식을 확인하세요."}
          </p>
          {!signup && new URLSearchParams(location.search).has("joined") && (
            <p className="auth-success" role="status">
              가입이 완료됐어요. 로그인해 주세요.
            </p>
          )}
          {signup && stage !== "password" ? (
            <form onSubmit={verifyEmail} aria-busy={busy}>
              <div className="auth-field" key="signup-email-field">
                <label htmlFor="signup-email">이메일</label>
                <input
                  id="signup-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  readOnly={stage === "code"}
                  disabled={busy}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  maxLength={320}
                  required
                />
              </div>
              {stage === "code" && (
                <div className="auth-field" key="verification-code-field">
                  <label htmlFor="code">인증번호</label>
                  <input
                    id="code"
                    name="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    placeholder="6자리 인증번호"
                    disabled={busy}
                    autoFocus
                    required
                  />
                </div>
              )}
              {mailNotice && (
                <p className="auth-success" role="status">
                  {mailNotice}
                </p>
              )}
              {error && (
                <p className="auth-error" role="alert">
                  {error}
                </p>
              )}
              <button className="auth-submit" disabled={busy}>
                {busy
                  ? "잠시만 기다려 주세요"
                  : stage === "email"
                    ? "인증번호 받기"
                    : "인증하고 계속하기"}
              </button>
              {stage === "code" && (
                <div className="auth-code-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={(e) => verifyEmail(e, true)}
                  >
                    인증번호 다시 받기
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setStage("email");
                      setError("");
                      setMailNotice("");
                    }}
                  >
                    이메일 변경
                  </button>
                </div>
              )}
            </form>
          ) : (
            <form onSubmit={submit} aria-busy={busy}>
              {signup && (
                <div className="auth-field">
                  <label htmlFor="displayName">이름</label>
                  <input
                    id="displayName"
                    name="displayName"
                    autoComplete="name"
                    placeholder="이름을 입력해 주세요"
                    maxLength={100}
                    required
                    aria-invalid={!!errors.displayName}
                    aria-describedby={
                      errors.displayName ? "name-error" : undefined
                    }
                  />
                  {errors.displayName && (
                    <p id="name-error" className="auth-field-error">
                      {errors.displayName}
                    </p>
                  )}
                </div>
              )}
              {signup ? (
                <p className="auth-verified">
                  ✓ {email}
                  <button
                    type="button"
                    onClick={() => {
                      setStage("email");
                      setProof("");
                      setError("");
                    }}
                  >
                    변경
                  </button>
                </p>
              ) : (
                <div className="auth-field">
                  <label htmlFor="email">이메일</label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    placeholder="name@example.com"
                    maxLength={320}
                    required
                  />
                </div>
              )}
              <div className="auth-field">
                <label htmlFor="password">비밀번호</label>
                <div className="auth-password">
                  <input
                    id="password"
                    name="password"
                    type={visible ? "text" : "password"}
                    autoComplete={signup ? "new-password" : "current-password"}
                    placeholder={
                      signup
                        ? "8자 이상 입력해 주세요"
                        : "비밀번호를 입력해 주세요"
                    }
                    required
                    aria-invalid={!!errors.password}
                    aria-describedby={
                      errors.password ? "password-error" : undefined
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setVisible(!visible)}
                    aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
                    aria-pressed={visible}
                  >
                    {visible ? "숨기기" : "보기"}
                  </button>
                </div>
                {errors.password && (
                  <p id="password-error" className="auth-field-error">
                    {errors.password}
                  </p>
                )}
              </div>
              {signup && (
                <div className="auth-field">
                  <label htmlFor="confirm">비밀번호 확인</label>
                  <input
                    id="confirm"
                    name="confirm"
                    type={visible ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="비밀번호를 한 번 더 입력해 주세요"
                    required
                    aria-invalid={!!errors.confirm}
                    aria-describedby={
                      errors.confirm ? "confirm-error" : undefined
                    }
                  />
                  {errors.confirm && (
                    <p id="confirm-error" className="auth-field-error">
                      {errors.confirm}
                    </p>
                  )}
                </div>
              )}
              {error && (
                <p className="auth-error" role="alert">
                  {error}
                </p>
              )}
              <button className="auth-submit" type="submit" disabled={busy}>
                {busy ? "잠시만 기다려 주세요" : signup ? "회원가입" : "로그인"}
              </button>
            </form>
          )}
          {!signup && (
            <p className="auth-switch">
              <a href="/?view=reset-password">비밀번호를 잊으셨나요?</a>
            </p>
          )}
          <p className="auth-switch">
            {signup ? "이미 계정이 있나요?" : "아직 계정이 없나요?"}
            <a href={signup ? "/?view=login" : "/?view=signup"}>
              {signup ? "로그인" : "회원가입"}
            </a>
          </p>
        </section>
      </main>
      <footer className="auth-footer">
        © {new Date().getFullYear()} ReGuard
      </footer>
    </div>
  );
}
