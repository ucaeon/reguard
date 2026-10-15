import React, { useEffect, useState } from "react";
import { catalogApi as api } from "../lib/catalog-api.js";
import { identifierLabel } from "../format.js";
import Picture from "./ProductPicture.jsx";
import CatalogRegistration from "../CatalogRegistration.jsx";

export default function ProductDetailDialog({ detail, setDetail }) {
  const [detailData, setDetailData] = useState(null);
  const [related, setRelated] = useState(null);
  const [detailError, setDetailError] = useState("");
  useEffect(() => {
    if (!detail) return;
    let active = true;
    const controller = new AbortController();
    const previous = document.activeElement;
    setDetailData(null);
    setRelated(null);
    setDetailError("");
    document.body.style.overflow = "hidden";
    document.querySelector(".close")?.focus();
    const key = (e) => {
      if (e.key === "Escape") setDetail(null);
      if (e.key === "Tab") {
        const els = [
          ...document.querySelectorAll(".modal button,.modal a[href]"),
        ];
        if (!els.length) return;
        const first = els[0],
          last = els.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    Promise.all([
      api(`/${detail.type}/${detail.id}`, { signal: controller.signal }),
      detail.type === "products"
        ? api(`/products/${detail.id}/recalls?size=20`, {
            signal: controller.signal,
          })
        : Promise.resolve(null),
    ])
      .then(([a, b]) => {
        if (active) {
          setDetailData(a);
          setRelated(b);
        }
      })
      .catch((e) => {
        if (active) setDetailError(e.message);
      });
    return () => {
      active = false;
      controller.abort();
      document.body.style.overflow = "";
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [detail]);

  if (!detail) return null;
  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) setDetail(null);
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
      >
        <button
          className="close"
          aria-label="상세 닫기"
          onClick={() => setDetail(null)}
        >
          ×
        </button>
        <div className="eyebrow">제품 정보</div>
        <h2 id="detail-title">
          {detailData?.name || detailData?.productName || "상세 정보"}
        </h2>
        {detailError ? (
          <p role="alert">
            {detailError}
            <button onClick={() => setDetail({ ...detail })}>다시 시도</button>
          </p>
        ) : !detailData ? (
          <p role="status">정보를 불러오고 있어요…</p>
        ) : (
          <>
            <div className="detail-image">
              <Picture
                url={detailData.imageUrl}
                name={detailData.name || detailData.productName}
              />
            </div>
            <dl>
              <dt>업체명</dt>
              <dd>{detailData.companyName || "정보 없음"}</dd>

              <dt>모델명</dt>
              <dd>{detailData.modelName || "정보 없음"}</dd>
              <dt>식별번호</dt>
              <dd>
                {detailData.identifiers?.length
                  ? detailData.identifiers.map((x, i) => (
                      <div key={i}>
                        {identifierLabel(x.type)} · {x.value}
                      </div>
                    ))
                  : "제공된 식별번호가 없어요."}
              </dd>
            </dl>

            <CatalogRegistration key={detail.id} productId={detail.id} />
            <h3 className="related-title">관련 리콜</h3>
            {related?.items.length ? (
              related.items.map((x) => (
                <button
                  className="related"
                  key={x.recall.id}
                  onClick={() =>
                    setDetail({ type: "recalls", id: x.recall.id })
                  }
                >
                  {x.recall.productName}
                  <span>대상 조건 확인 필요 ↗</span>
                </button>
              ))
            ) : (
              <p className="info">
                현재 연결된 리콜 정보가 없어요. 제품의 안전을 보장하는 의미는
                아니에요.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
