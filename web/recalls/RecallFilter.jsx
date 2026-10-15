import React, { useState } from "react";
const dateKey = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const periods = [
  ["all", "전체"],
  ["week", "1주"],
  ["month", "1개월"],
  ["quarter", "3개월"],
  ["year", "1년"],
  ["custom", "직접 설정"],
];
function rangeFor(period, now = new Date()) {
  if (period === "all") return { from: "", to: "" };
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const start = new Date(end);
  if (period === "week") start.setDate(start.getDate() - 6);
  else {
    const months = { month: 1, quarter: 3, year: 12 }[period];
    start.setDate(1);
    start.setMonth(start.getMonth() - months);
    start.setDate(
      Math.min(
        end.getDate(),
        new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate(),
      ),
    );
  }
  return { from: dateKey(start), to: dateKey(end) };
}
function selectedPeriod(value) {
  return (
    periods
      .filter(([key]) => key !== "custom")
      .find(([key]) => {
        const range = rangeFor(key);
        return range.from === value.from && range.to === value.to;
      })?.[0] || "custom"
  );
}
export default function RecallFilter({ value, onApply }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [target, setTarget] = useState(null);
  const [period, setPeriod] = useState(() => selectedPeriod(value));
  const appliedCount =
    Number(!!value.source) + Number(!!(value.from || value.to));
  const [month, setMonth] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const first = new Date(month.getFullYear(), month.getMonth(), 1).getDay();
  const count = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0,
  ).getDate();
  const invalid = draft.from && draft.to && draft.from > draft.to;
  const chooseTarget = (key) => {
    setTarget(target === key ? null : key);
    if (draft[key]) {
      const [y, m] = draft[key].split("-").map(Number);
      setMonth(new Date(y, m - 1, 1));
    }
  };
  return (
    <div className="recall-filter-area">
      <button
        className="recall-filter-toggle"
        type="button"
        aria-expanded={open}
        aria-controls="recall-filter-panel"
        onClick={() => {
          if (!open) {
            setDraft(value);
            setPeriod(selectedPeriod(value));
          }
          setOpen(!open);
          setTarget(null);
        }}
      >
        필터 {appliedCount > 0 && <b className="rf-count">{appliedCount}</b>}{" "}
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <form
          id="recall-filter-panel"
          className="rf-panel"
          onSubmit={(e) => {
            e.preventDefault();
            if (!invalid) {
              onApply(draft);
              setOpen(false);
              setTarget(null);
            }
          }}
        >
          <fieldset>
            <legend>물건 카테고리</legend>
            <div className="rf-options">
              {[
                ["", "전체"],
                ["FOOD_I0490", "식품"],
                ["SAFETY_RECALL", "생활용품·어린이 제품"],
              ].map(([key, label]) => (
                <button
                  type="button"
                  key={key}
                  aria-pressed={draft.source === key}
                  onClick={() => setDraft({ ...draft, source: key })}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>기간</legend>
            <div className="rf-options rf-periods">
              {periods.map(([key, label]) => (
                <button
                  type="button"
                  key={key}
                  aria-pressed={period === key}
                  onClick={() => {
                    setPeriod(key);
                    setTarget(null);
                    if (key !== "custom")
                      setDraft({ ...draft, ...rangeFor(key) });
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            {period !== "all" && period !== "custom" && (
              <p className="rf-range-summary">
                {draft.from.replaceAll("-", ".")} —{" "}
                {draft.to.replaceAll("-", ".")}
              </p>
            )}
            {period === "custom" && (
              <div className="rf-dates">
                {[
                  ["from", "시작일"],
                  ["to", "종료일"],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-expanded={target === key}
                    aria-controls="rf-calendar"
                    className={target === key ? "is-open" : ""}
                    onClick={() => chooseTarget(key)}
                  >
                    <span>{label}</span>
                    <strong>
                      {draft[key]?.replaceAll("-", ".") || "날짜 선택"}
                    </strong>
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      aria-hidden="true"
                    >
                      <rect x="3" y="5" width="18" height="16" rx="3" />
                      <path d="M7 3v4m10-4v4M3 11h18" />
                    </svg>
                  </button>
                ))}
              </div>
            )}
            {target && (
              <div id="rf-calendar" className="rf-calendar">
                <div className="rf-month">
                  <button
                    type="button"
                    aria-label="이전 달"
                    onClick={() =>
                      setMonth(
                        new Date(month.getFullYear(), month.getMonth() - 1, 1),
                      )
                    }
                  >
                    ‹
                  </button>
                  <strong aria-live="polite">
                    {month.getFullYear()}년 {month.getMonth() + 1}월
                  </strong>
                  <button
                    type="button"
                    aria-label="다음 달"
                    onClick={() =>
                      setMonth(
                        new Date(month.getFullYear(), month.getMonth() + 1, 1),
                      )
                    }
                  >
                    ›
                  </button>
                </div>
                <div className="rf-days">
                  {["일", "월", "화", "수", "목", "금", "토"].map((d) => (
                    <span key={d}>{d}</span>
                  ))}
                  {Array.from({ length: first }, (_, i) => (
                    <span key={`blank${i}`} />
                  ))}
                  {Array.from({ length: count }, (_, i) => {
                    const key = dateKey(
                      new Date(month.getFullYear(), month.getMonth(), i + 1),
                    );
                    const disabled =
                      target === "to"
                        ? !!draft.from && key < draft.from
                        : !!draft.to && key > draft.to;
                    return (
                      <button
                        type="button"
                        key={key}
                        disabled={disabled}
                        aria-label={`${key} 선택`}
                        aria-pressed={draft[target] === key}
                        className={key === dateKey(new Date()) ? "today" : ""}
                        onClick={() => {
                          setDraft({ ...draft, [target]: key });
                          setTarget(
                            target === "from" && !draft.to ? "to" : null,
                          );
                        }}
                      >
                        {i + 1}
                      </button>
                    );
                  })}
                </div>
                <button
                  className="rf-clear-date"
                  type="button"
                  onClick={() => setDraft({ ...draft, [target]: "" })}
                >
                  날짜 지우기
                </button>
              </div>
            )}
          </fieldset>
          <div className="recall-filter-actions">
            <button
              type="button"
              onClick={() => {
                setDraft({ source: "", from: "", to: "" });
                setPeriod("all");
                setTarget(null);
              }}
            >
              초기화
            </button>
            <button type="submit" disabled={!!invalid}>
              결과 보기
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
