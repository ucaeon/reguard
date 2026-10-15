import { apiRequest, getCsrf } from "./lib/api-client.js";
import React, { useState } from "react";

export default function CatalogRegistration({ productId }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loginRequired, setLoginRequired] = useState(false);
  const [saved, setSaved] = useState(false);
  async function register() {
    if (busy || saved) return;
    setBusy(true);
    setError("");
    setLoginRequired(false);
    try {
      const csrf = await getCsrf(
        "/api/v1/auth/csrf",
        "서버 연결을 확인해 주세요.",
      );
      const response = await apiRequest("/api/v1/me/products", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          [csrf.headerName]: csrf.token,
        },
        body: JSON.stringify({
          registrationType: "CATALOG",
          catalogProductId: productId,
        }),
      });
      if (response.status === 401) {
        setLoginRequired(true);
        throw new Error("로그인한 후 물건을 등록할 수 있어요.");
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          data.message || "등록하지 못했어요. 다시 시도해 주세요.",
        );
      }
      setSaved(true);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="catalog-registration">
      {saved ? (
        <p role="status">
          내 물건에 등록했어요. <a href="/?view=items">내 물건 보기 →</a>
        </p>
      ) : (
        <button className="primary" onClick={register} disabled={busy}>
          {busy ? "등록 중…" : "내 물건에 등록"}
        </button>
      )}
      {error && (
        <p role="alert">
          {error} {loginRequired && <a href="/?view=login">로그인 →</a>}
        </p>
      )}
    </div>
  );
}
