import { navigateTo } from "../lib/navigation.js";
import { useProfile } from "../auth/ProfileProvider.jsx";
import { profileStore } from "../lib/profile-store.js";
import { mutateJson } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import NotificationPreferences from "./NotificationPreferences.jsx";
import React, { useEffect, useState, useRef } from "react";
import "./settings.css";
export default function SettingsPage() {
  const { profile, loading, error: profileError } = useProfile();
  const login = !profile && !profileError;
  const [name, setName] = useState(""),
    [photo, setPhoto] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [passwordOpen, setPasswordOpen] = useState(false);
  const lock = useRef(false);
  const initialized = useRef(null);
  useEffect(() => {
    if (!profile) initialized.current = null;
    if (profile && initialized.current !== profile.id) {
      initialized.current = profile.id;
      setName(profile.displayName);
      setPhoto(profile.photo);
    }
  }, [profile]);
  function change(path, method, body) {
    return mutateJson(path, method, body, {
      serverMessage: true,
      message: "저장하지 못했어요. 다시 시도해 주세요.",
      statusMessages: { 401: "다시 로그인해 주세요." },
    });
  }
  async function save(e) {
    e.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await change("/api/v1/me/profile", "PUT", {
        displayName: name.trim(),
        photo,
      });
      profileStore.update(data);
      setName(data.displayName);
      setPhoto(data.photo);
      setNotice("프로필을 저장했어요.");
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function pick(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    if (
      !["image/jpeg", "image/png"].includes(file.type) ||
      file.size > 1048576
    ) {
      setError("1MB 이하의 JPG 또는 PNG 사진을 선택해 주세요.");
      return;
    }
    setBusy(true);
    try {
      const result = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("사진을 읽지 못했어요."));
        reader.readAsDataURL(file);
      });
      setPhoto(result);
      setNotice("사진을 적용하려면 저장해 주세요.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function password(e) {
    e.preventDefault();
    if (lock.current) return;
    const form = e.currentTarget,
      values = Object.fromEntries(new FormData(form));
    setError("");
    setNotice("");
    if (values.newPassword !== values.confirm) {
      setError("새 비밀번호가 일치하지 않아요.");
      return;
    }
    lock.current = true;
    setBusy(true);
    try {
      await change("/api/v1/me/profile/password", "POST", {
        currentPassword: values.currentPassword,
        newPassword: values.newPassword,
      });
      navigateTo("/?view=login");
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="settings-page">
      <SiteHeader active="settings" variant="settings" />
      <main className="settings-main">
        <h1>설정</h1>
        <p className="settings-description">내 프로필과 계정을 관리하세요.</p>
        {loading ? (
          <p role="status">계정 정보를 불러오고 있어요…</p>
        ) : !profile ? (
          <section>
            <p role="alert">
              {error ||
                (profileError
                  ? "계정 정보를 불러오지 못했어요."
                  : "로그인하고 계정 정보를 관리하세요.")}
            </p>
            {login ? (
              <a href="/?view=login">로그인 →</a>
            ) : (
              <button onClick={() => profileStore.refresh()}>다시 시도</button>
            )}
          </section>
        ) : (
          <>
            <section>
              <h2>내 프로필</h2>
              <form onSubmit={save}>
                <fieldset disabled={busy}>
                  <div className="settings-photo">
                    {photo ? (
                      <img src={photo} alt="프로필 사진" />
                    ) : (
                      <span
                        className="settings-avatar"
                        aria-label="기본 프로필"
                      >
                        {name.trim().slice(0, 1) || "R"}
                      </span>
                    )}
                    <div>
                      <label className="settings-upload">
                        사진 변경
                        <input
                          type="file"
                          accept="image/png,image/jpeg"
                          onChange={pick}
                        />
                      </label>
                      {photo && (
                        <button
                          type="button"
                          className="settings-text-button"
                          onClick={() => {
                            setPhoto(null);
                            setNotice("저장을 누르면 사진이 삭제돼요.");
                          }}
                        >
                          사진 삭제
                        </button>
                      )}
                      <p>JPG·PNG / 1MB 이하 / 최대 2048px</p>
                    </div>
                  </div>
                  <label className="settings-field">
                    닉네임
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      maxLength={100}
                      autoComplete="nickname"
                    />
                  </label>
                  <label className="settings-field">
                    이메일
                    <input value={profile.email} readOnly type="email" />
                  </label>
                  <p className="settings-hint">가입 시 인증한 이메일이에요.</p>
                  <div className="settings-save-row">
                    <button
                      type="submit"
                      className="settings-save"
                      disabled={busy || !name.trim()}
                    >
                      {busy ? "처리 중…" : "저장"}
                    </button>
                  </div>
                </fieldset>
              </form>
            </section>
            <NotificationPreferences />
            <section>
              <button
                className="settings-section-button"
                onClick={() => setPasswordOpen(!passwordOpen)}
                aria-expanded={passwordOpen}
              >
                비밀번호 변경 <span>{passwordOpen ? "−" : "＋"}</span>
              </button>
              {passwordOpen && (
                <form onSubmit={password}>
                  <fieldset disabled={busy}>
                    {[
                      ["currentPassword", "현재 비밀번호", "current-password"],
                      ["newPassword", "새 비밀번호", "new-password"],
                      ["confirm", "새 비밀번호 확인", "new-password"],
                    ].map(([key, label, auto]) => (
                      <label className="settings-field" key={key}>
                        {label}
                        <input
                          name={key}
                          type="password"
                          autoComplete={auto}
                          required
                          minLength={key === "currentPassword" ? undefined : 8}
                        />
                      </label>
                    ))}
                    <p className="settings-hint">
                      변경하면 모든 기기에서 로그아웃돼요.
                    </p>
                    <button className="settings-save" type="submit">
                      비밀번호 변경
                    </button>
                  </fieldset>
                </form>
              )}
            </section>
            {error && (
              <p className="settings-error" role="alert">
                {error}
              </p>
            )}
            {notice && (
              <p className="settings-notice" role="status">
                {notice}
              </p>
            )}
          </>
        )}
        <section className="settings-info">
          <h2>서비스 정보</h2>
          <a href="/?view=about">
            ReGuard 이용 가이드 <span>↗</span>
          </a>
        </section>
      </main>
    </div>
  );
}
