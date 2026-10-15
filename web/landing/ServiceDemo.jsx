import React, { useEffect, useRef, useState } from "react";
import "./service-demo.css";

import { captures, scenes } from "./service-demo-scenes.js";

export default function ServiceDemo({ scene, label, active = true }) {
  const root = useRef(null);
  const [visible, setVisible] = useState(false);
  const [seen, setSeen] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState(false);
  const frames = scenes[scene];
  const currentIndex = index % frames.length;
  const duration = captures[frames[currentIndex]].duration || 5000;
  const playing =
    active && visible && pageVisible && !paused && !reduced && !failed;

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotion = () => setReduced(motion.matches);
    const updateVisibility = () => setPageVisible(!document.hidden);
    updateMotion();
    updateVisibility();
    motion.addEventListener("change", updateMotion);
    document.addEventListener("visibilitychange", updateVisibility);
    const observer = new IntersectionObserver(
      ([entry]) => {
        setVisible(entry.isIntersecting);
        if (entry.isIntersecting) setSeen(true);
      },
      { threshold: 0.2 },
    );
    observer.observe(root.current);
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", updateMotion);
      document.removeEventListener("visibilitychange", updateVisibility);
    };
  }, []);

  useEffect(() => {
    if (!playing || frames.length < 2) return;
    const timer = window.setTimeout(
      () => setIndex((value) => (value + 1) % frames.length),
      duration,
    );
    return () => window.clearTimeout(timer);
  }, [playing, frames.length, index, duration]);

  useEffect(() => {
    setIndex(0);
    setPaused(false);
  }, [active, visible]);

  return (
    <section
      ref={root}
      className={`lp-screen service-demo service-demo--${scene} ${playing ? "is-playing" : ""}`}
      aria-label={`${label} 미리보기`}
    >
      <div className="lp-screen-bar">
        <i aria-hidden="true" />
        <i aria-hidden="true" />
        <i aria-hidden="true" />
        <span>ReGuard</span>
        <small>실제 서비스 화면</small>
        {!reduced && (
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            aria-label={paused ? `${label} 모션 재생` : `${label} 모션 멈춤`}
          >
            {paused ? "재생 ▷" : "멈춤 Ⅱ"}
          </button>
        )}
      </div>
      <div className="service-demo-stage">
        {failed ? (
          <p className="service-demo-error">
            화면을 불러오지 못했어요. 새로고침해 주세요.
          </p>
        ) : (
          seen &&
          frames.map((name, frameIndex) => {
            const {
              width,
              height,
              cursor,
              caption,
              file = name,
              imageHeight = height,
              duration: frameDuration = 5000,
            } = captures[name];
            return (
              <svg
                key={name}
                className={`service-demo-capture ${currentIndex === frameIndex ? "is-current" : ""}`}
                viewBox={`0 0 ${width} ${height}`}
                style={{
                  "--frame-duration": `${frameDuration}ms`,
                  "--scroll-y": `${height - imageHeight}px`,
                }}
                role="img"
                aria-label={caption}
                aria-hidden={currentIndex !== frameIndex}
              >
                <g
                  className={
                    imageHeight > height && currentIndex === frameIndex
                      ? "service-demo-scroll"
                      : ""
                  }
                >
                  <image
                    href={`/images/service-demo/${file}.jpg`}
                    width={width}
                    height={imageHeight}
                    onError={() => setFailed(true)}
                  />
                </g>
                {currentIndex === frameIndex && cursor && (
                  <g
                    transform={`translate(${cursor.join(" ")})`}
                    aria-hidden="true"
                  >
                    <g className="service-demo-pointer">
                      <circle
                        className="service-demo-click"
                        r="23"
                        fill="none"
                        stroke="#0b7972"
                        strokeWidth="3"
                      />
                      <path
                        d="M0 0 8 32 15 23 27 34 33 28 21 17 33 14Z"
                        fill="#152f32"
                        stroke="white"
                        strokeWidth="3"
                        strokeLinejoin="round"
                      />
                    </g>
                  </g>
                )}
              </svg>
            );
          })
        )}
      </div>
      <div className="service-demo-controls">
        <p>{captures[frames[currentIndex]].caption}</p>

      </div>
    </section>
  );
}
