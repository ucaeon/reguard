import { apiRequest } from "../lib/api-client.js";
import SiteHeader from "../components/SiteHeader.jsx";
import React, { useEffect, useState, useRef } from "react";
import RecallReason from "./RecallReason.jsx";
import { recallReturnUrl } from "../list-navigation.js";
import {
  conditionText,
  recallName,
  recallFallback,
  verifiedRecallPhotos,
} from "../format.js";
const safeLink = (value) => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
};
export default function RecallDetailPage({ id }) {
  const [data, setData] = useState(null);
  const [zoom, setZoom] = useState(null);
  const zoomDialog = useRef(null);
  useEffect(() => {
    if (!zoom) return;
    const previous = document.activeElement;
    zoomDialog.current?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [zoom]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    setImageFailed(false);
    apiRequest(`/api/v1/recalls/${encodeURIComponent(id)}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "리콜 정보를 찾을 수 없어요."
              : "리콜 정보를 불러오지 못했어요.",
          );
        return response.json();
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [id, retry]);
  useEffect(() => {
    document.title = data
      ? `${recallName(data)} · 리콜 정보 | ReGuard`
      : "리콜 상세 | ReGuard";
    return () => {
      document.title = "ReGuard";
    };
  }, [data]);
  const source =
    data?.source === "FOOD_I0490" ? "식품안전나라" : "Safety Korea";
  const sourceUrl = safeLink(data?.sourceUrl);
  const conditions = data
    ? conditionText(data.targetConditions).split("\n")
    : [];
  return (
    <div className="about-page recall-document">
      <SiteHeader active="recall" variant="about" />
      <main className="recall-document-main">
        <a
          className="rd-back"
          href={
            new URLSearchParams(location.search).get("from") === "notifications"
              ? "/?view=notifications"
              : recallReturnUrl(location.search)
          }
        >
          {new URLSearchParams(location.search).get("from") === "notifications"
            ? "← 알림 목록"
            : "← 리콜 목록"}
        </a>
        {error ? (
          <div className="rd-load" role="alert">
            <h1>{error}</h1>
            <button onClick={() => setRetry(retry + 1)}>다시 시도</button>
          </div>
        ) : !data ? (
          <p className="rd-load" role="status">
            리콜 정보를 불러오고 있어요…
          </p>
        ) : (
          <>
            <div className="rd-page-heading">
              <p>리콜 정보</p>
              <h1>{recallName(data)}</h1>
              {data.companyName && <p>{data.companyName}</p>}
            </div>
            <div className="rd-page-intro">
              <button
                type="button"
                className="rd-page-photo"
                aria-label="제품 사진 크게 보기"
                onClick={() =>
                  setZoom(
                    (!imageFailed && safeLink(data.imageUrl)) ||
                      recallFallback(data),
                  )
                }
              >
                {safeLink(data.imageUrl) && !imageFailed ? (
                  <img
                    src={safeLink(data.imageUrl)}
                    alt={recallName(data)}
                    onError={() => setImageFailed(true)}
                  />
                ) : (
                  <img src={recallFallback(data)} alt="카테고리 기본 이미지" />
                )}
              </button>
              <div className="rd-page-summary">
                <h2 className="rr-section-title">리콜 이유</h2>
                <RecallReason reason={data.reason} />
                <dl>
                  <dt>분류</dt>
                  <dd>
                    {data.source === "FOOD_I0490"
                      ? "식품"
                      : "생활용품·어린이 제품"}
                  </dd>
                  <dt>제공 기관</dt>
                  <dd>{source}</dd>
                  {data.sourceCreatedAt && (
                    <>
                      <dt>공표일</dt>
                      <dd>
                        <time dateTime={data.sourceCreatedAt}>
                          {new Date(data.sourceCreatedAt).toLocaleDateString(
                            "ko-KR",
                          )}
                        </time>
                      </dd>
                    </>
                  )}
                </dl>
              </div>
            </div>
            {verifiedRecallPhotos(data).length > 1 && (
              <section className="rd-page-section">
                <div>
                  <h2>공식 부분 사진</h2>
                </div>
                <div>
                  <button
                    type="button"
                    className="rd-zoom-trigger"
                    aria-label="부분 사진 크게 보기"
                    onClick={() => setZoom(verifiedRecallPhotos(data)[1])}
                  >
                    <img
                      className="rd-label-photo"
                      src={verifiedRecallPhotos(data)[1]}
                      alt="허니 슬라임 공식 공고의 부분 사진"
                    />
                  </button>
                </div>
              </section>
            )}
            <section className="rd-page-section">
              <div>
                <span>01</span>
                <h2>대상 조건</h2>
              </div>
              <div>
                <p className="rd-page-guide">
                  제품 라벨에 적힌 정보와 아래 조건을 비교해 주세요.
                </p>
                <dl className="rd-condition-table">
                  {conditions.map((line, i) => {
                    const split = line.indexOf(":");
                    return split > 0 ? (
                      <React.Fragment key={i}>
                        <dt>{line.slice(0, split)}</dt>
                        <dd>{line.slice(split + 1).trim()}</dd>
                      </React.Fragment>
                    ) : (
                      <dd className="rd-condition-full" key={i}>
                        {line}
                      </dd>
                    );
                  })}
                </dl>
              </div>
            </section>
            <section className="rd-page-section">
              <div>
                <span>02</span>
                <h2>조치 방법</h2>
              </div>
              <div>
                <p className="rd-page-action">
                  {data.actionMethod ||
                    "제공된 조치 방법이 없어요. 아래 제공 기관에서 해당 제품의 공고를 확인해 주세요."}
                </p>
              </div>
            </section>
            <section className="rd-page-section rd-page-source">
              <div>
                <span>03</span>
                <h2>공고 확인</h2>
              </div>
              <div>
                <p className="rd-page-guide">
                  {sourceUrl
                    ? "문의처와 자세한 절차는 원문에서 확인할 수 있어요."
                    : `${source}에서 제품명으로 공고를 찾아 문의처와 자세한 절차를 확인해 주세요.`}
                </p>
                <a
                  className="rd-source"
                  href={
                    sourceUrl ||
                    (data.source === "FOOD_I0490"
                      ? "https://www.foodsafetykorea.go.kr/"
                      : "https://www.safetykorea.kr/")
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {sourceUrl ? "리콜 원문 보기" : `${source} 바로가기`}{" "}
                  <span aria-hidden="true">↗</span>
                </a>
              </div>
            </section>
          </>
        )}
      </main>
      {zoom && (
        <dialog
          ref={zoomDialog}
          className="rd-lightbox"
          aria-label="제품 사진 확대"
          onCancel={() => setZoom(null)}
          onClick={(event) => {
            if (event.target === event.currentTarget) setZoom(null);
          }}
        >
          <button
            type="button"
            autoFocus
            aria-label="확대 사진 닫기"
            onClick={() => setZoom(null)}
          >
            ×
          </button>
          <img
            src={zoom}
            alt={`${data ? recallName(data) : "제품"} 확대 사진`}
          />
        </dialog>
      )}
    </div>
  );
}
