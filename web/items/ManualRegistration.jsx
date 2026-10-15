import { apiRequest, getCsrf } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import React, { useState } from "react";
import "./manual-registration.css";
const initialValues = {
  productName: "",
  companyName: "",
  modelName: "",
  identifierValue: "",
  expiryDate: "",
  lotNumber: "",
};
export default function ManualRegistration() {
  const [values, setValues] = useState(() => ({
      ...initialValues,
      productName: (
        new URLSearchParams(location.search).get("name") || ""
      ).slice(0, 500),
    })),
    [kind, setKind] = useState("food"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [login, setLogin] = useState(false),
    [saved, setSaved] = useState(null);
  function field(name, label, placeholder, required = false, type = "text") {
    return (
      <label className="mr-field" key={name}>
        <span>
          {label}
          {required ? <b>필수</b> : <small>선택</small>}
        </span>
        <input
          name={name}
          type={type}
          required={required}
          maxLength={
            name === "identifierValue" || name === "lotNumber" ? 255 : 500
          }
          value={values[name]}
          placeholder={placeholder}
          onChange={(e) => setValues({ ...values, [name]: e.target.value })}
        />
      </label>
    );
  }
  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    setError("");
    setLogin(false);
    if (!values.productName.trim()) {
      setError("제품명을 입력해 주세요.");
      return;
    }
    setBusy(true);
    try {
      const csrf = await getCsrf(
        "/api/v1/auth/csrf",
        "서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
      );
      const body = {
        registrationType: "MANUAL",
        productName: values.productName.trim(),
      };
      for (const name of ["companyName", "modelName", "lotNumber"])
        if (values[name].trim() && (name !== "modelName" || kind !== "food"))
          body[name] = values[name].trim();
      if (kind === "food" && values.expiryDate)
        body.expiryDate = values.expiryDate;
      if (values.identifierValue.trim()) {
        body.identifierValue = values.identifierValue.trim();
        body.identifierType = kind === "food" ? "FOOD_REPORT_NO" : "KC_CERT_NO";
      }
      const response = await apiRequest("/api/v1/me/products", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          [csrf.headerName]: csrf.token,
        },
        body: JSON.stringify(body),
      });
      if (response.status === 401) {
        setLogin(true);
        throw new Error("물건을 저장하려면 로그인해 주세요.");
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          data.message ||
            "등록하지 못했어요. 입력 내용을 확인하고 다시 시도해 주세요.",
        );
      }
      setSaved(await response.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="about-page">
      <SiteHeader active="items" variant="about" />
      <main className="mr-main">
        <a className="mr-back" href="/?view=items">
          ← 내 물건
        </a>
        {saved ? (
          <section className="mr-success" role="status">
            <span>✓</span>
            <h1>물건을 등록했어요</h1>
            <p>{saved.productName}</p>
            <p>입력한 정보가 계정에 저장됐어요.</p>
            <button
              onClick={() => {
                setSaved(null);
                setValues(initialValues);
              }}
            >
              다른 물건 등록
            </button>
            <a href="/?view=items">내 물건으로</a>
          </section>
        ) : (
          <>
            <h1>직접 등록</h1>
            <p className="mr-lead">
              제품 포장이나 라벨에 적힌 정보를 입력해 주세요.
            </p>
            <form onSubmit={submit} aria-busy={busy}>
              <fieldset disabled={busy}>
                <legend>제품 정보</legend>
                <div className="mr-category">
                  <span>제품 종류</span>
                  <div>
                    {[
                      ["food", "식품"],
                      ["goods", "생활용품·어린이 제품"],
                    ].map(([value, label]) => (
                      <label key={value}>
                        <input
                          type="radio"
                          name="kind"
                          value={value}
                          checked={kind === value}
                          onChange={() => {
                            setKind(value);
                            setValues({ ...values, identifierValue: "" });
                          }}
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                {field("productName", "제품명", "포장에 적힌 제품명", true)}
                {field("companyName", "제조·수입업체명", "라벨에 적힌 업체명")}
                <div className="mr-section-title">
                  <h2>제품을 구분하는 정보</h2>
                  <p>알고 있는 항목만 입력해도 괜찮아요.</p>
                </div>
                {kind === "goods" &&
                  field("modelName", "모델명", "예: ABC-100")}
                {field(
                  "identifierValue",
                  kind === "food" ? "품목보고번호" : "KC 인증번호",
                  kind === "food" ? "숫자로 입력" : "예: CB065R2649-4001",
                )}
                {kind === "food" &&
                  field("expiryDate", "소비기한", "", false, "date")}
                {field("lotNumber", "제조번호 (LOT)", "포장에 적힌 제조번호")}
                {error && (
                  <div className="mr-error" role="alert">
                    {error}
                    {login && (
                      <a
                        href="/?view=login"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        새 탭에서 로그인 ↗
                      </a>
                    )}
                  </div>
                )}
                <div className="mr-actions">
                  <a href="/?view=search">제품 검색으로 찾기</a>
                  <button type="submit" disabled={busy}>
                    {busy ? "등록 중…" : "내 물건에 등록"}
                  </button>
                </div>
              </fieldset>
            </form>
          </>
        )}
      </main>
    </div>
  );
}
