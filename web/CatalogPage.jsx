import { navigateTo } from "./lib/navigation.js";
import useCatalogResults from "./useCatalogResults.js";
import Picture from "./components/ProductPicture.jsx";
import Search from "./components/ProductSearch.jsx";
import ProductDetailDialog from "./components/ProductDetailDialog.jsx";
import "./styles/tokens.css";
import SiteHeader from "./components/SiteHeader.jsx";
import React, { useState } from "react";
import "./style.css";
import "./recalls/recalls.css";
import RecallFilter from "./recalls/RecallFilter.jsx";
import {
  readListState,
  listUrl,
  rememberListPosition,
} from "./list-navigation.js";
import useListPersistence from "./useListPersistence.js";
import { recallName, recallSummary, recallFallback } from "./format.js";

export default function CatalogPage({ view }) {
  const [initialList] = useState(() => readListState(location.search));
  const [q, setQ] = useState(initialList.term);
  const [term, setTerm] = useState(initialList.term);
  const [page, setPage] = useState(initialList.page);
  const [category, setCategory] = useState(initialList.category);
  const [recallSource, setRecallSource] = useState(initialList.source);
  const [recallFilters, setRecallFilters] = useState({
    sort: "latest",
    from: initialList.from,
    to: initialList.to,
  });
  const [retry, setRetry] = useState(0);
  const { data, loading, error } = useCatalogResults({
    view,
    term,
    page,
    category,
    recallSource,
    recallFilters,
    retry,
  });
  const [detail, updateDetail] = useState(null);
  const currentListUrl = ["recalls", "search"].includes(view)
    ? listUrl({
        view,
        term,
        page,
        category,
        source: recallSource,
        ...recallFilters,
      })
    : null;
  useListPersistence(currentListUrl, !!data && !loading);
  function setDetail(next) {
    if (next?.type === "recalls") {
      rememberListPosition(currentListUrl);
      const params = new URLSearchParams({ view: "recall", id: next.id });
      if (view === "recalls") params.set("returnTo", currentListUrl);
      navigateTo(`/?${params}`);
    } else updateDetail(next);
  }

  function search(v = q) {
    if (!v.trim() && view !== "recalls") return;
    setQ(v);
    setTerm(v.trim());
    setPage(0);
  }

  return (
    <>
      <SiteHeader active={view} variant="compact" />

      <main>
        <section
          className={`results ${view === "recalls" ? "recall-results" : ""}`}
        >
          <h1>{view === "recalls" ? "리콜 정보" : "제품 검색"}</h1>
          <Search
            value={q}
            onChange={setQ}
            onSearch={() => search()}
            required={view !== "recalls"}
            placeholder={
              view === "recalls"
                ? "제품명 또는 업체명 검색"
                : "제품명 · 업체명 · 인증번호"
            }
          />
          {view === "recalls" && (
            <RecallFilter
              value={{ source: recallSource, ...recallFilters }}
              onApply={(value) => {
                setRecallSource(value.source);
                setRecallFilters({
                  sort: "latest",
                  from: value.from,
                  to: value.to,
                });
                setPage(0);
              }}
            />
          )}
          {view === "search" && (
            <div className="filters">
              {[
                ["", "전체"],
                ["FOOD", "일반 식품"],
                ["HEALTH_SUPPLEMENT", "건강기능식품"],
              ].map(([v, t]) => (
                <button
                  key={v}
                  className={category === v ? "selected" : ""}
                  onClick={() => {
                    setCategory(v);
                    setPage(0);
                  }}
                >
                  {t}
                </button>
              ))}
              <small>KC 제품은 ‘전체’에서 검색해요</small>
            </div>
          )}
          {loading ? (
            <div className="state" role="status">
              검색 중…
            </div>
          ) : error ? (
            <div className="state" role="alert">
              {error}{" "}
              <button type="button" onClick={() => setRetry((x) => x + 1)}>
                다시 시도
              </button>
            </div>
          ) : !term && view === "search" ? (
            <div className="state">궁금한 제품의 이름을 입력해보세요.</div>
          ) : data?.items.length === 0 ? (
            <div className="state">
              <h2>검색 결과가 없습니다.</h2>
              <p>
                다른 제품명이나 업체명으로 다시 검색해보세요.
                <br />
                검색 결과가 없다고 안전한 제품을 의미하지는 않아요.
              </p>
              {view === "search" && (
                <a
                  className="manual-register-link"
                  href={`/?view=register&name=${encodeURIComponent(term)}`}
                >
                  직접 등록 <span aria-hidden="true">→</span>
                </a>
              )}
            </div>
          ) : data ? (
            <>
              <div className="result-title">
                {term ? `‘${term}’ 검색 결과` : "전체 리콜"}{" "}
                <span>
                  {view !== "recalls" &&
                    `${page + 1}페이지 · ${data.items.length}개 표시`}
                </span>
              </div>
              <div className="products">
                {data.items.map((p) => (
                  <button
                    className="product-card"
                    key={p.id}
                    onClick={() =>
                      setDetail({
                        type: view === "recalls" ? "recalls" : "products",
                        id: p.id,
                      })
                    }
                  >
                    <div className="product-photo">
                      <Picture
                        url={p.imageUrl}
                        name={view === "recalls" ? recallName(p) : p.name}
                        fallback={
                          view === "recalls" ? recallFallback(p) : undefined
                        }
                      />
                    </div>
                    <div className="card-body">
                      <small>{p.companyName || "업체 정보 없음"}</small>
                      <h3>{view === "recalls" ? recallName(p) : p.name}</h3>
                      <p className={view === "recalls" ? "recall-reason" : ""}>
                        {view === "recalls"
                          ? recallSummary(p.reason)
                          : p.modelName || ""}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
              <div className="pagination">
                <button
                  disabled={view === "recalls" ? page < 3 : page === 0}
                  onClick={() => {
                    setPage(
                      view === "recalls"
                        ? Math.max(0, (Math.floor(page / 3) - 1) * 3)
                        : page - 1,
                    );
                    document
                      .querySelector(".results")
                      ?.scrollIntoView({ block: "start" });
                  }}
                >
                  ← 이전
                </button>
                {view === "recalls" ? (
                  <div className="page-numbers">
                    {data.pageNumbers.map((number) => (
                      <button
                        key={number}
                        type="button"
                        aria-label={`${number + 1}페이지`}
                        aria-current={page === number ? "page" : undefined}
                        onClick={() => {
                          setPage(number);
                          document
                            .querySelector(".results")
                            ?.scrollIntoView({ block: "start" });
                        }}
                      >
                        {number + 1}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span>{page + 1}</span>
                )}
                <button
                  disabled={
                    view === "recalls" ? !data.hasNextGroup : !data.hasNext
                  }
                  onClick={() => {
                    setPage(
                      view === "recalls"
                        ? (Math.floor(page / 3) + 1) * 3
                        : page + 1,
                    );
                    document
                      .querySelector(".results")
                      ?.scrollIntoView({ block: "start" });
                  }}
                >
                  다음 →
                </button>
              </div>
            </>
          ) : null}
        </section>
      </main>

      <footer>
        <span>© 2026 ReGuard</span>
        <span>식품안전나라 · Safety Korea</span>
      </footer>

      <ProductDetailDialog detail={detail} setDetail={setDetail} />
    </>
  );
}
