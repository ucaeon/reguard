import { navigateTo } from "../lib/navigation.js";
import { MainNavigation } from "../components/SiteHeader.jsx";
import AccountMenu from "../AccountMenu.jsx";
import React, { useEffect, useRef, useState } from "react";
import "./landing.css";
import BrandMark from "../BrandMark.jsx";
import ServiceDemo from "./ServiceDemo.jsx";

const steps = [
  [
    "물건을 검색하세요",
    "제품명이나 포장에 적힌 인증번호로 검색해 보세요. 검색 결과에서 내가 쓰는 제품을 찾을 수 있어요.",
    "제품 검색 화면",
  ],
  [
    "정보를 확인하세요",
    "이름이 같아도 다른 제품일 수 있어요. 제조업체와 모델명을 내 물건의 포장·라벨과 비교해 주세요.",
    "제품 정보 화면",
  ],
  [
    "내 물건에 등록하세요",
    "검색되지 않는 제품은 포장·라벨에 적힌 제품명과 인증번호 등을 직접 입력해 내 물건에 등록하세요.",
    "수동 등록 화면",
  ],
];
const sections = ["intro", "why", "register", "recall", "alerts"];

function ScrollWriting({ lines }) {
  const heading = useRef(null);

  useEffect(() => {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const letters = [...heading.current.querySelectorAll("[data-letter]")];
    let frame = 0;
    const update = () => {
      frame = 0;
      const track = heading.current.closest(".lp-writing-track");
      const top = track.getBoundingClientRect().top;
      const distance = Math.max(1, track.offsetHeight - innerHeight);
      const progress = reduced.matches
        ? 1
        : Math.max(0, Math.min(1, -top / distance));
      const writingProgress = Math.min(1, progress / 0.85);
      const count = Math.round(writingProgress * letters.length);
      heading.current.classList.toggle(
        "is-complete",
        count > "잘 쓰고 있던 물건".replaceAll(" ", "").length,
      );
      letters.forEach((letter, index) => {
        letter.classList.toggle("is-written", index < count);
        letter.classList.toggle(
          "has-caret",
          count > 0 && count < letters.length && index === count - 1,
        );
      });
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    reduced.addEventListener("change", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      reduced.removeEventListener("change", schedule);
    };
  }, []);

  return (
    <h2
      className="lp-scroll-writing"
      ref={heading}
      aria-label={lines.join(" ")}
    >
      {lines.map((line) => (
        <span className="lp-writing-line" key={line} aria-hidden="true">
          {line.split(" ").map((word, index) => (
            <React.Fragment key={index}>
              {index > 0 && " "}
              <span className="lp-writing-word">
                {[...word].map((letter, letterIndex) => (
                  <span data-letter key={letterIndex}>
                    {letter}
                  </span>
                ))}
              </span>
            </React.Fragment>
          ))}
        </span>
      ))}
    </h2>
  );
}

export default function LandingPage() {
  const root = useRef(null);
  const register = useRef(null);
  const hero = useRef(null);
  const [step, setStep] = useState(0);
  const [active, setActive] = useState("intro");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const cards = [...root.current.querySelectorAll(".lp-pain-grid article")];
    const grid = root.current.querySelector(".lp-pain-grid");
    const bridge = root.current.querySelector(".lp-bridge-section");
    const thread = root.current.querySelector(".lp-scroll-thread");
    const main = root.current.querySelector(".lp-main");
    const painEyebrow = root.current.querySelector(
      ".lp-pain-heading .lp-eyebrow",
    );
    const scenes = ["recall", "alerts"].map((id) =>
      document.getElementById(id),
    );
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = register.current.getBoundingClientRect();
      const travel = Math.max(1, rect.height - window.innerHeight);
      const progress = Math.max(0, Math.min(1, -rect.top / travel));
      if (!reduced.matches && window.innerWidth > 700) {
        setStep(Math.min(2, Math.floor(progress * 3)));
      }
      const heroProgress = Math.min(
        1,
        Math.max(
          0,
          -hero.current.parentElement.getBoundingClientRect().top /
            Math.max(
              innerHeight,
              hero.current.parentElement.offsetHeight - innerHeight,
            ),
        ),
      );
      hero.current.style.setProperty(
        "--hero-progress",
        reduced.matches ? 0 : heroProgress,
      );
      hero.current.style.setProperty(
        "--hero-exit",
        reduced.matches
          ? 0
          : Math.max(0, Math.min(1, (heroProgress - 0.15) / 0.75)),
      );
      hero.current.style.setProperty(
        "--hero-fade",
        reduced.matches
          ? 0
          : Math.max(0, Math.min(1, (heroProgress - 0.5) / 0.4)),
      );
      hero.current.style.setProperty(
        "--hero-zoom",
        reduced.matches
          ? 1
          : 1 + 0.3 * Math.max(0, Math.min(1, (heroProgress - 0.1) / 0.4)),
      );
      hero.current.style.setProperty(
        "--text-exit",
        reduced.matches
          ? 0
          : Math.max(0, Math.min(1, (heroProgress - 0.5) / 0.45)),
      );
      const mainTop = main.getBoundingClientRect().top;
      const heroBottom =
        hero.current.parentElement.getBoundingClientRect().bottom;
      const lineStart = heroBottom - innerHeight * 0.4;
      const lineEnd = painEyebrow.getBoundingClientRect().top - 24;
      const lineHeight = Math.max(0, lineEnd - lineStart);
      thread.style.top = `${lineStart - mainTop}px`;
      thread.style.height = `${lineHeight}px`;
      thread.style.setProperty(
        "--thread-progress",
        reduced.matches
          ? 1
          : Math.max(
              0,
              Math.min(
                1,
                (innerHeight * 0.8 - lineStart) / Math.max(1, lineHeight),
              ),
            ),
      );
      const bridgeProgress = Math.max(
        0,
        Math.min(
          1,
          (innerHeight * 0.65 - bridge.getBoundingClientRect().top) /
            (bridge.offsetHeight - innerHeight * 0.35),
        ),
      );
      const phase = (start, duration) =>
        Math.max(0, Math.min(1, (bridgeProgress - start) / duration));
      bridge.style.setProperty(
        "--bridge-lead",
        reduced.matches ? 1 : phase(0, 0.22),
      );
      bridge.style.setProperty(
        "--bridge-main",
        reduced.matches ? 1 : phase(0.16, 0.24),
      );
      bridge.style.setProperty(
        "--bridge-exit",
        reduced.matches ? 0 : phase(0.8, 0.2),
      );
      const track = grid.parentElement;
      const storyProgress = Math.max(
        0,
        Math.min(
          1,
          -track.getBoundingClientRect().top /
            Math.max(1, track.offsetHeight - innerHeight),
        ),
      );
      const stage = Math.min(2, Math.floor(storyProgress * 3));
      cards.forEach((card, index) => {
        const visible = reduced.matches || index === stage;
        card.classList.toggle("is-current", visible);
        card.setAttribute("aria-hidden", String(!visible));
      });
      scenes.forEach((scene) => {
        const progress = reduced.matches
          ? 1
          : Math.max(
              0,
              Math.min(
                1,
                (innerHeight * 0.9 - scene.getBoundingClientRect().top) /
                  (innerHeight * 0.85),
              ),
            );
        scene.style.setProperty("--scene-progress", progress);
        scene.style.setProperty(
          "--late-progress",
          Math.max(0, Math.min(1, (progress - 0.35) / 0.65)),
        );
      });
      let current = "intro";
      sections.forEach((id) => {
        if (
          document.getElementById(id).getBoundingClientRect().top <=
          window.innerHeight * 0.5
        )
          current = id;
      });
      setActive(current);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    root.current
      .querySelectorAll("[data-reveal]")
      .forEach((el) => observer.observe(el));
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        setNotice("");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const start = () => {
    navigateTo("/?view=login");
  };
  const jump = (id) => {
    document.getElementById(id).scrollIntoView({
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  };

  return (
    <div className="lp" ref={root}>
      <a className="lp-skip" href="#intro">
        본문으로 이동
      </a>
      <header className="lp-header site-header-layout">
        <a
          className="lp-logo"
          href="#intro"
          onClick={(e) => {
            e.preventDefault();
            jump("intro");
          }}
        >
          <BrandMark />
        </a>
        <nav
          className="lp-nav site-main-nav"
          aria-label="주 메뉴"
          id="landing-navigation"
        >
          <MainNavigation buttons />
        </nav>
        <div className="lp-account">
          <AccountMenu />
        </div>
      </header>
      <nav className="lp-position" aria-label="소개 구간">
        {sections.map((id, i) => (
          <button
            key={id}
            onClick={() => jump(id)}
            aria-label={
              ["처음", "리콜이란", "물건 등록", "리콜 확인", "알림"][i]
            }
            aria-current={active === id ? "step" : undefined}
          >
            <span />
          </button>
        ))}
      </nav>
      <main className="lp-main">
        <div className="lp-scroll-thread" aria-hidden="true">
          <span />
        </div>
        <div className="lp-hero-track" id="intro">
          <section className="lp-hero" ref={hero}>
            <div className="lp-hero-copy">
              <h1>
                매일 쓰는 물건
                <br />
                <em>계속 써도 괜찮을까?</em>
              </h1>
            </div>
            <div className="lp-hero-photo" aria-hidden="true">
              <img
                src="/images/everyday-table-cool.png"
                alt=""
                fetchPriority="high"
                width="1536"
                height="1024"
              />
            </div>
            <button
              className="lp-scroll-cue"
              aria-label="리콜 설명으로 스크롤"
              onClick={() => jump("why")}
            >
              <span aria-hidden="true">↓</span>
            </button>
          </section>
        </div>
        <section className="lp-pain" id="why">
          <div className="lp-writing-track">
            <div className="lp-pain-heading">
              <p className="lp-eyebrow">리콜 나와 먼 이야기가 아니에요</p>
              <ScrollWriting
                lines={[
                  "잘 쓰고 있던 물건에도",
                  "안전 문제가 발견될 수 있어요.",
                ]}
              />
              <p className="lp-pain-definition">
                판매된 제품에서 안전 문제가 발견돼 회수하거나 수리·교환하는
                조치를 <strong>‘리콜’</strong>이라고 해요.
                <br />
                이미 구매한 물건도 대상일 수 있어 내가 쓰는 제품인지 확인하는
                것이 중요해요.
              </p>
            </div>
          </div>
          <div className="lp-pain-story">
            <div className="lp-pain-grid">
              <article>
                <div className="lp-story-copy">
                  <span className="lp-pain-number">01</span>
                  <h3>샀을 때는 몰랐던 문제</h3>
                  <p>
                    겉으로 멀쩡해 보여도 유해 성분이나 과열 위험이 뒤늦게 발견될
                    수 있어요.
                    <br />
                    구매할 때 확인했더라도 사용 중인 물건의 새로운 리콜 소식을
                    살펴볼 필요가 있어요.
                  </p>
                  <div className="lp-pain-label">
                    구매 이후에도 확인이 필요해요
                  </div>
                </div>
                <div
                  className="lp-story-art lp-warning-art"
                  aria-label="슬라임 제품에서 안전 문제가 발견되는 예시"
                >
                  <div className="lp-toy-body">
                    <div className="lp-cute-face">
                      <i />
                      <i />
                      <b />
                    </div>
                    <span className="lp-slime-shine" />
                  </div>
                  <div className="lp-warning-badge">
                    <b className="lp-warning-icon" aria-hidden="true">
                      !
                    </b>
                    <span>안전 문제 발견</span>
                  </div>
                </div>
              </article>
              <article>
                <div className="lp-story-copy">
                  <span className="lp-pain-number">02</span>
                  <h3>여기저기 흩어진 소식</h3>
                  <p>
                    식품과 생활제품의 리콜 소식은 서로 다른 기관에서 알려주기
                    때문에 직접 찾아보기 번거로워요.
                    <br />
                    ReGuard는 여러 곳에 흩어진 리콜 정보를 모아 한곳에서 확인할
                    수 있게 해요.
                  </p>
                  <div className="lp-pain-label">필요한 정보를 한곳에서</div>
                </div>
                <div
                  className="lp-story-art lp-gather-art"
                  role="img"
                  aria-label="여러 곳의 안전 정보가 ReGuard로 모이는 모습"
                >
                  <div className="lp-gather-orbit" aria-hidden="true" />
                  {[0, 1, 2, 3].map((item) => (
                    <div
                      className={`lp-info-fragment lp-info-fragment-${item}`}
                      key={item}
                      aria-hidden="true"
                    >
                      <span />
                      <i />
                      <i />
                    </div>
                  ))}
                  <div className="lp-gather-core">
                    <BrandMark compact />
                  </div>
                </div>
              </article>
              <article>
                <div className="lp-story-copy">
                  <span className="lp-pain-number">03</span>
                  <h3>내 물건인지 헷갈릴 때</h3>
                  <p>
                    제품 이름이 같아도 모델명·제조일자·소비기한에 따라 리콜
                    대상이 달라질 수 있어요.
                    <br />
                    ReGuard에서 대상 조건을 확인하고 내 물건의 라벨과 비교해
                    보세요.
                  </p>
                  <div className="lp-pain-label">제품 정보와 대상 조건까지</div>
                </div>
                <div
                  className="lp-story-art lp-label-art"
                  aria-label="제품 라벨의 모델명과 제조일자를 리콜 조건과 비교하는 예시"
                >
                  <div className="lp-label-sheet">
                    <span className="lp-art-caption">내 물건의 라벨</span>
                    <strong>휴대용 보조배터리</strong>
                    <div className="lp-barcode" aria-hidden="true" />
                    <dl>
                      <div>
                        <dt>모델명</dt>
                        <dd>RG–100</dd>
                      </div>
                      <div>
                        <dt>제조일자</dt>
                        <dd>2026. 08. 31</dd>
                      </div>
                    </dl>
                  </div>
                  <div className="lp-condition-sheet">
                    <span className="lp-art-caption">리콜 대상 조건</span>
                    <strong>이 두 가지를 확인해 주세요</strong>
                    <div>
                      <span>01</span>제품의 모델명
                    </div>
                    <div>
                      <span>02</span>제조일자 · 대상 기간
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </section>
        <section className="lp-bridge-section" aria-label="ReGuard 소개">
          <p className="lp-pain-bridge">
            <span className="lp-bridge-lead">그래서 ReGuard는</span>
            <strong>내 물건에서부터 시작해요.</strong>
          </p>
        </section>
        <section className="lp-registration" id="register" ref={register}>
          <div className="lp-sticky">
            <div className="lp-registration-copy">
              <p className="lp-eyebrow">내 물건 등록</p>
              <h2>
                찾아서 등록하면
                <br />
                관리는 간편하게.
              </h2>
              <div className="lp-steps">
                {steps.map(([title, desc], i) => (
                  <div
                    className={`lp-step ${step === i ? "is-active" : ""}`}
                    key={title}
                  >
                    <span>0{i + 1}</span>
                    <div>
                      <h3>
                        <button
                          type="button"
                          aria-pressed={step === i}
                          onClick={() => {
                            setStep(i);
                            if (
                              !matchMedia("(prefers-reduced-motion: reduce)")
                                .matches &&
                              innerWidth > 700
                            ) {
                              const section = register.current;
                              const top =
                                scrollY + section.getBoundingClientRect().top;
                              const travel = Math.max(
                                1,
                                section.offsetHeight - innerHeight,
                              );
                              window.scrollTo({
                                top: top + (travel * (i + 0.15)) / 3,
                                behavior: "instant",
                              });
                            }
                          }}
                        >
                          {title}
                        </button>
                      </h3>
                      <p>{desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="lp-step-stage">
              {steps.map(([, , label], i) => (
                <div
                  key={label}
                  className={`lp-step-screen ${step === i ? "is-active" : ""}`}
                  aria-hidden={step !== i}
                  inert={step !== i}
                >
                  <ServiceDemo
                    scene={["search", "product", "registered"][i]}
                    label={label}
                    active={step === i}
                  />
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="lp-recall" id="recall">
          <div className="lp-scene-pin">
            <div className="lp-section-inner">
              <div className="lp-recall-visual">
                <ServiceDemo scene="recall" label="리콜 상세 화면" />
              </div>
              <div className="lp-section-copy">
                <p className="lp-eyebrow">리콜 정보 확인</p>
                <h2>
                  왜 리콜됐는지
                  <br />내 물건도 해당하는지.
                </h2>
                <p className="lp-description">
                  어떤 안전 문제가 발견됐는지, 어느 제품이 회수 대상인지 함께
                  확인하세요.
                  <br />
                  제조일자·소비기한 등 공고의 대상 조건과 안내된 조치 방법도
                  살펴볼 수 있어요.
                </p>
                <div className="lp-tags">
                  <span>리콜 사유</span>
                  <span>제조일자·소비기한</span>
                  <span>조치 방법</span>
                </div>
              </div>
            </div>
          </div>
        </section>
        <section className="lp-alerts" id="alerts">
          <div className="lp-scene-pin">
            <div className="lp-alert-copy">
              <p className="lp-eyebrow">나에게 필요한 알림</p>
              <h2>
                내 물건과 관련된 소식만
                <br />
                놓치지 않게.
              </h2>
              <p className="lp-description">
                등록한 내 물건과 관련된 새 리콜이나 공고 변경이 있으면
                알림함에서 알려드려요.
                <br />
                알림을 열어 대상 조건을 확인하고 내 제품에 해당하는지
                살펴보세요.
              </p>
            </div>
            <div className="lp-alert-visual">
              <ServiceDemo scene="alerts" label="맞춤 알림 화면" />
              <div className="lp-alert-slot" aria-label="리콜 알림">
                <span className="lp-notification-icon" aria-hidden="true">
                  ↗
                </span>
                <span>내 물건의 리콜 소식</span>
                <span className="lp-slot-dot" />
              </div>
            </div>
          </div>
        </section>
        <section className="lp-end" data-reveal>
          <h2>
            지금 내 물건부터
            <br />
            확인해보세요.
          </h2>
          <button className="lp-button" onClick={start}>
            시작하기 <span aria-hidden="true">→</span>
          </button>
        </section>
      </main>
      <footer className="lp-footer">
        <a className="lp-logo" href="#intro">
          <BrandMark />
        </a>
        <p>공공데이터 출처 · 식품안전나라 · Safety Korea</p>
        <span>© {new Date().getFullYear()} ReGuard</span>
      </footer>
      {notice && (
        <div className="lp-notice" role="status">
          {notice}
          <button onClick={() => setNotice("")} aria-label="안내 닫기">
            ×
          </button>
        </div>
      )}
    </div>
  );
}
