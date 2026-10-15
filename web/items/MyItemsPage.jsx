import { apiRequest } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import React, { useState, useEffect } from "react";
import OwnedProductDialog from "./OwnedProductDialog.jsx";
import "./my-items.css";
import {
  loadOwnedProducts,
  ownedCategory,
  ownedRecallLinks,
} from "./owned-products.js";
export default function MyItemsPage() {
  const [items, setItems] = useState([]);
  const [action, setAction] = useState(null),
    [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [unauthorized, setUnauthorized] = useState(false),
    [retry, setRetry] = useState(0);
  const [checks, setChecks] = useState({});
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") setRetry((x) => x + 1);
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setUnauthorized(false);
    setChecks({});
    loadOwnedProducts(controller.signal)
      .then(async (rows) => {
        setItems(
          rows.map((row) => ({
            ...row,
            name: row.productName,
            company: row.companyName || "",
            category: ownedCategory(row),
          })),
        );
        setLoading(false);
        let index = 0;
        async function worker() {
          while (index < rows.length && !controller.signal.aborted) {
            const item = rows[index++];
            let result;
            try {
              const response = await apiRequest(
                `/api/v1/me/products/${encodeURIComponent(item.id)}/recalls`,
                {
                  credentials: "include",
                  cache: "no-store",
                  signal: controller.signal,
                },
              );
              if (!response.ok) throw new Error();
              result = await response.json();
            } catch (e) {
              if (controller.signal.aborted) return;
              result = { lookupStatus: "ERROR", items: [] };
            }
            if (!controller.signal.aborted)
              setChecks((old) => ({ ...old, [item.id]: result }));
          }
        }
        await Promise.all(
          Array.from({ length: Math.min(4, rows.length) }, worker),
        );
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(e.message);
          setUnauthorized(e.status === 401);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [retry]);
  const noticeCount = items.filter(
    (item) => checks[item.id]?.items?.length > 0,
  ).length;
  const checking =
    !loading && !error && Object.keys(checks).length < items.length;
  function status(item) {
    const check = checks[item.id];
    if (!check) return "리콜 정보를 확인하고 있어요.";
    if (check.lookupStatus === "ERROR") return "리콜 정보를 확인하지 못했어요.";
    if (check.lookupStatus === "INSUFFICIENT_DETAILS")
      return "리콜 확인에 필요한 정보가 부족해요.";
    return check.items.length
      ? "관련 리콜의 대상 조건을 확인해 주세요."
      : "조회된 관련 리콜이 없어요.";
  }
  const [tab, setTab] = useState("전체");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("전체 카테고리");
  const [selected, setSelected] = useState(null);
  const shown = items.filter(
    (item) =>
      (tab !== "리콜 확인" || checks[item.id]?.items?.length > 0) &&
      (category === "전체 카테고리" || item.category === category) &&
      `${item.name} ${item.company}`.includes(query.trim()),
  );
  return (
    <div className="about-page mi-page">
      <SiteHeader active="items" variant="about" />
      <main className="mi-main">
        <div className="mi-heading">
          <div>
            <h1>내 물건</h1>
            <p>내가 쓰는 물건의 리콜 소식을 한곳에서.</p>
          </div>
          <a className="mi-add" href="/?view=search">
            <span aria-hidden="true">＋</span> 물건 등록
          </a>
        </div>
        <div className="mi-summary">
          <button onClick={() => setTab("전체")} aria-pressed={tab === "전체"}>
            <span>전체 물건</span>
            <strong>
              {loading || error ? "—" : items.length}
              <small>개</small>
            </strong>
          </button>
          <button
            onClick={() => setTab("리콜 확인")}
            aria-pressed={tab === "리콜 확인"}
          >
            <span>리콜 확인</span>
            <strong className={noticeCount ? "mi-attention" : ""}>
              {loading || error || checking ? "—" : noticeCount}
              <small>개</small>
            </strong>
            <span className="mi-summary-arrow" aria-hidden="true">
              ↗
            </span>
          </button>
        </div>
        <div className="mi-toolbar">
          <div className="mi-tabs" aria-label="물건 상태">
            {["전체", "리콜 확인"].map((label) => (
              <button
                key={label}
                aria-pressed={tab === label}
                className={tab === label ? "is-active" : ""}
                onClick={() => setTab(label)}
              >
                {label}
                {label === "리콜 확인" && noticeCount > 0 && (
                  <span>{noticeCount}</span>
                )}
              </button>
            ))}
          </div>
        </div>
        {message && (
          <p className="mi-feedback" role="status">
            {message}
          </p>
        )}
        <div className="mi-controls">
          <label className="mi-search">
            <svg
              width="19"
              height="19"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <circle cx="10.5" cy="10.5" r="6.5" />
              <path d="m16 16 5 5" />
            </svg>
            <input
              aria-label="내 물건 검색"
              placeholder="내 물건 검색"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="물건 카테고리"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {["전체 카테고리", "식품", "생활용품·어린이 제품"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <section className="mi-empty" role="status">
            <p>내 물건을 불러오고 있어요…</p>
          </section>
        ) : error ? (
          <section className="mi-empty" role="alert">
            <h2>{error}</h2>
            {unauthorized ? (
              <a href="/?view=login">로그인</a>
            ) : (
              <button
                className="mi-reset"
                onClick={() => setRetry((x) => x + 1)}
              >
                다시 시도
              </button>
            )}
          </section>
        ) : items.length === 0 ? (
          <section className="mi-empty">
            <div className="mi-empty-art" aria-hidden="true">
              <svg viewBox="0 0 96 96" fill="none">
                <path
                  d="m18 34 30-16 30 16v34L48 84 18 68V34Z"
                  fill="#f1f5f4"
                  stroke="#a9bdb8"
                  strokeWidth="2"
                />
                <path
                  d="m18 34 30 16 30-16M48 50v34M33 26l30 16v15"
                  stroke="#a9bdb8"
                  strokeWidth="2"
                />
                <circle cx="73" cy="69" r="17" fill="white" />
                <path
                  d="M73 61v16m-8-8h16"
                  stroke="#0f766e"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <h2>첫 번째 물건을 등록해 보세요</h2>
            <p>물건을 등록하고, 관련 리콜을 확인하세요.</p>
          </section>
        ) : shown.length === 0 ? (
          <section className="mi-empty">
            <h2>
              {checking && tab === "리콜 확인"
                ? "리콜 정보를 확인하고 있어요"
                : "조건에 맞는 물건이 없어요"}
            </h2>
            <button
              className="mi-reset"
              onClick={() => {
                setQuery("");
                setCategory("전체 카테고리");
                setTab("전체");
              }}
            >
              전체 물건 보기
            </button>
          </section>
        ) : (
          <div className="mi-list">
            {shown.map((item) => (
              <article className="mi-row" key={item.id}>
                <img
                  src={`/images/recall-${/슬라임/.test(item.name) ? "slime" : item.category === "식품" ? "food" : "toy"}.svg`}
                  alt="제품 기본 이미지"
                />
                <div className="mi-product">
                  <p>{item.company}</p>
                  <h2>{item.name}</h2>
                  <span>{status(item)}</span>
                </div>
                <button
                  className={
                    checks[item.id]?.items?.length
                      ? "mi-status mi-status-alert"
                      : "mi-status"
                  }
                  onClick={() =>
                    setSelected(selected === item.id ? null : item.id)
                  }
                  aria-expanded={selected === item.id}
                >
                  {checks[item.id]?.items?.length ? "리콜 확인" : "등록 정보"}{" "}
                  <span aria-hidden="true">↗</span>
                </button>
                {selected === item.id && (
                  <div className="mi-expanded">
                    <div className="mi-item-actions">
                      <button onClick={() => setAction({ item, mode: "edit" })}>
                        정보 수정
                      </button>
                      <button
                        className="mi-remove"
                        onClick={() => setAction({ item, mode: "delete" })}
                      >
                        삭제
                      </button>
                    </div>
                    <dl>
                      {[
                        ["제품명", item.productName],
                        ["업체명", item.companyName],
                        ["모델명", item.modelName],
                        ["식별번호", item.identifierValue],
                        ["소비기한", item.expiryDate],
                        ["제조번호", item.lotNumber],
                      ]
                        .filter(([, value]) => value)
                        .map(([label, value]) => (
                          <React.Fragment key={label}>
                            <dt>{label}</dt>
                            <dd>{value}</dd>
                          </React.Fragment>
                        ))}
                    </dl>
                    {ownedRecallLinks(checks[item.id]).map((recall) => (
                      <a
                        className="mi-recall-link"
                        key={recall.id}
                        href={`/?view=recall&id=${encodeURIComponent(recall.id)}`}
                      >
                        {recall.productName || "리콜 대상 조건 확인"} →
                      </a>
                    ))}
                    {checks[item.id]?.lookupStatus === "ERROR" && (
                      <button
                        className="mi-reset"
                        onClick={() => setRetry((x) => x + 1)}
                      >
                        리콜 다시 확인
                      </button>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </main>
      {action && (
        <OwnedProductDialog
          item={action.item}
          mode={action.mode}
          onClose={() => setAction(null)}
          onSuccess={(text) => {
            setAction(null);
            setMessage(text);
            setSelected(null);
            setRetry((x) => x + 1);
          }}
        />
      )}
    </div>
  );
}
