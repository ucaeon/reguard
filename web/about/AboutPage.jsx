import SiteHeader from "../components/SiteHeader.jsx";
import React, { useEffect, useState } from "react";
import BrandMark from "../BrandMark.jsx";
import "./about.css";

const contents = [
  ["overview", "시작하기"],
  ["why", "왜 필요한가요?"],
  ["products", "확인할 수 있는 제품"],
  ["how", "제품 검색과 등록"],
  ["action", "리콜 소식 확인하기"],
  ["faq", "자주 묻는 질문"],
];
const pains = [
  [
    "구매할 때는 몰랐던 안전 문제",
    "구매 당시에는 문제를 몰랐던 제품도 판매 이후에 유해 성분이나 결함이 발견될 수 있어요. 이미 사용 중인 물건도 새로운 리콜 소식을 확인할 필요가 있어요.",
  ],
  [
    "여러 곳에 흩어진 리콜 소식",
    "식품과 생활용품의 리콜 정보는 서로 다른 곳에서 제공돼요. 여러 사이트를 직접 찾아봐야 해서 내 물건과 관련된 소식을 놓치기 쉬워요.",
  ],
  [
    "내 제품이 대상인지 헷갈리는 조건",
    "제품 이름이 같아도 모델명·제조일자·소비기한에 따라 리콜 대상이 달라질 수 있어요. 공고의 조건과 내 제품의 라벨을 비교해야 해요.",
  ],
];
const steps = [
  [
    "내 물건을 검색해요",
    "제품명이나 업체명 또는 포장에 적힌 인증번호로 찾아보세요. 검색 결과에서 내 제품과 이름·업체·모델이 일치하는지 확인해요.",
  ],
  [
    "내 물건에 등록해요",
    "찾은 제품을 저장해 관리해요. 검색되지 않는 제품은 제품 정보를 직접 입력해 등록할 수 있어요.",
  ],
  [
    "관련 리콜 소식을 확인해요",
    "등록한 물건과 관련된 리콜 소식은 알림함에서 확인해요. 알림을 열면 리콜 사유와 대상 조건을 살펴볼 수 있어요.",
  ],
];
const faqs = [
  [
    "검색되지 않는 물건도 등록할 수 있나요?",
    "제품 정보를 직접 입력해 등록할 수 있어요. 제품명과 모델명 등 라벨에 적힌 정보를 정확히 입력하면 내 물건을 구분하는 데 도움이 돼요. 등록만으로 모든 리콜 정보를 자동으로 찾을 수 있는 것은 아니에요.",
  ],
  [
    "제품 이름이 같으면 모두 리콜 대상인가요?",
    "아니요. 같은 이름의 제품도 모델명·제조일자·소비기한·제조번호 등에 따라 대상이 달라질 수 있어요. 공고에 명시된 조건과 실제 제품의 정보를 함께 비교해 주세요.",
  ],
  [
    "리콜 정보가 없으면 안전한 제품인가요?",
    "리콜 정보가 없다는 것이 제품의 안전을 보증하는 것은 아니에요. 아직 문제가 알려지지 않았거나 제공되는 정보에 포함되지 않았을 수 있어요.",
  ],
  [
    "어디에서 제공한 정보를 볼 수 있나요?",
    "식품안전나라와 Safety Korea 등 공공기관에서 제공하는 제품·리콜 정보를 바탕으로 안내해요. 대상 여부와 구체적인 조치 방법은 해당 리콜 공고를 기준으로 확인해 주세요.",
  ],
  [
    "ReGuard에서 교환이나 환불도 신청하나요?",
    "ReGuard는 관련 정보를 찾아 확인하도록 돕는 서비스예요. 회수·교환·환불 등은 공고에 안내된 판매처나 제조업체의 절차에 따라 진행해 주세요.",
  ],
];

export default function AboutPage() {
  const [active, setActive] = useState("overview");
  useEffect(() => {
    const update = () => {
      let current = "overview";
      for (const [id] of contents) {
        if (
          document.getElementById(`about-${id}`)?.getBoundingClientRect().top <=
          180
        )
          current = id;
      }
      setActive(current);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  return (
    <div className="about-page">
      <a className="about-skip" href="#about-content">
        본문으로 이동
      </a>
      <SiteHeader active="about" variant="about" />
      <div className="about-layout">
        <aside className="about-index">
          <p>이용 가이드</p>
          <nav aria-label="이 페이지 목차">
            {contents.map(([id, name], i) => (
              <a
                key={id}
                href={`#about-${id}`}
                aria-current={active === id ? "location" : undefined}
              >
                {name}
              </a>
            ))}
          </nav>
        </aside>
        <main id="about-content" className="about-content">
          <section id="about-overview" className="about-overview">
            <p className="about-eyebrow">이용 가이드 / 시작하기</p>
            <h1>ReGuard 시작하기</h1>
            <p className="about-lead">
              제품을 찾고 내 물건에 등록한 뒤 관련 리콜 소식을 확인하는 방법을
              안내해요.
            </p>
            <p>
              처음 이용한다면 아래 순서대로 시작해 보세요. 제품명과 모델명이
              적힌 라벨을 준비하면 더 정확하게 확인할 수 있어요.
            </p>
            <ol className="about-flow">
              <li>
                <a href="#about-how">
                  <span>01</span>제품 검색과 등록 <b aria-hidden="true">↗</b>
                </a>
              </li>
              <li>
                <a href="#about-action">
                  <span>02</span>리콜 소식 확인 <b aria-hidden="true">↗</b>
                </a>
              </li>
              <li>
                <a href="#about-faq">
                  <span>03</span>자주 묻는 질문 <b aria-hidden="true">↗</b>
                </a>
              </li>
            </ol>
          </section>
          <section id="about-why">
            <h2>왜 필요한가요?</h2>
            <div className="about-reasons">
              {pains.map(([title, text], i) => (
                <article key={title}>
                  <span className="about-number">0{i + 1}</span>
                  <div>
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                </article>
              ))}
            </div>
            <p className="about-note">
              ReGuard는 흩어진 정보를 모으고{" "}
              <strong>내 물건을 기준으로 확인할 수 있게</strong> 도와줘요.
            </p>
          </section>
          <section id="about-products">
            <h2>어떤 물건을 확인할 수 있나요?</h2>
            <p>
              먹는 것부터 매일 사용하는 생활용품까지 제품 정보와 리콜 소식을
              살펴볼 수 있어요.
              <br />
              제품 정보와 리콜 소식은 매일 업데이트돼요.
            </p>
            <div className="about-products">
              <article>
                <h3>식품·건강기능식품</h3>
                <p>
                  제품명과 제조업체를 확인하고 소비기한 등 리콜 대상 조건을
                  비교해요.
                </p>
              </article>
              <article>
                <h3>생활용품·어린이 제품</h3>
                <p>
                  모델명이나 인증번호로 제품을 구분하고 관련 안전 정보를
                  확인해요.
                </p>
              </article>
            </div>
          </section>
          <section id="about-how">
            <h2>제품 검색과 등록</h2>
            <ol className="about-steps">
              {steps.map(([title, text], i) => (
                <li key={title}>
                  <span>{i + 1}</span>
                  <div>
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <a className="about-text-link" href="/?view=search">
              제품 검색해 보기 <span aria-hidden="true">→</span>
            </a>
          </section>
          <section id="about-action">
            <h2>리콜 소식 확인하기</h2>
            <p>
              리콜은 판매된 제품의 안전 문제로 회수하거나 수리·교환 등의 조치를
              하는 것을 말해요. 관련 소식을 받으면 다음 순서로 확인해 주세요.
            </p>
            <ol className="about-checklist">
              <li>
                <strong>내 제품의 라벨을 확인해요.</strong>
                <p>
                  모델명·제조일자·소비기한·제조번호 등 공고에서 요구하는 정보를
                  찾아요.
                </p>
              </li>
              <li>
                <strong>공고의 대상 조건과 비교해요.</strong>
                <p>
                  제품 이름뿐 아니라 대상 기간과 모델까지 일치하는지 살펴봐요.
                </p>
              </li>
              <li>
                <strong>안내된 조치 방법을 따라요.</strong>
                <p>
                  공고에 나온 사용 중단·회수·수리·교환 방법과 문의처를 확인해요.
                </p>
              </li>
            </ol>
          </section>
          <section id="about-faq">
            <h2>자주 묻는 질문</h2>
            <div className="about-faq">
              {faqs.map(([q, a]) => (
                <details key={q}>
                  <summary>{q}</summary>
                  <p>{a}</p>
                </details>
              ))}
            </div>
          </section>
          <div className="about-end">
            <h2>준비됐다면 제품을 찾아보세요</h2>
            <a href="/?view=search">
              제품 검색하기 <span aria-hidden="true">→</span>
            </a>
          </div>
        </main>
      </div>
      <footer className="about-footer">
        <BrandMark />
        <span>© {new Date().getFullYear()} ReGuard</span>
      </footer>
    </div>
  );
}
