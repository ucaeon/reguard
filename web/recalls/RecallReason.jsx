import React from "react";
import { parseRecallReason, reasonFieldLabel } from "./recall-reason.js";

export default function RecallReason({ reason }) {
  const blocks = parseRecallReason(reason);
  if (!blocks.length)
    return <p className="rr-empty">제공된 리콜 이유가 없어요.</p>;
  return (
    <div className="recall-reason-explanation">
      {blocks.map((block, index) => (
        <section
          className="rr-issue"
          key={index}
          aria-labelledby={`rr-title-${index}`}
        >
          <h3 id={`rr-title-${index}`}>
            {blocks.length > 1 && (
              <span className="rr-number">
                {String(index + 1).padStart(2, "0")}
              </span>
            )}
            {block.explanation || block.title}
          </h3>
          {block.explanation && block.fields.length > 0 && (
            <p className="rr-official-heading">{block.title}</p>
          )}
          {block.fields.length > 0 && (
            <dl className="rr-facts">
              {block.fields.map((field, i) => (
                <React.Fragment key={i}>
                  <dt>{reasonFieldLabel(field.label)}</dt>
                  <dd
                    className={
                      reasonFieldLabel(field.label) === "검사 결과"
                        ? "rr-measured"
                        : undefined
                    }
                  >
                    {field.label === "측정값"
                      ? field.value.replace(/,\s*(?=(?:MIT|CMIT))/g, ",\n")
                      : field.value}
                  </dd>
                </React.Fragment>
              ))}
            </dl>
          )}
          {block.notes.map((note, i) => (
            <p className="rr-note" key={i}>
              {note}
            </p>
          ))}
        </section>
      ))}
      <details className="rr-original">
        <summary>공고 원문 보기</summary>
        <p>{reason}</p>
      </details>
    </div>
  );
}
