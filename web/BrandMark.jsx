import React from "react";
import "./brand.css";

export default function BrandMark({ compact = false }) {
  return (
    <span className={`rg-brand${compact ? " rg-brand-compact" : ""}`}>
      <img
        className="rg-brand-mark"
        src="/brand/reguard-mark.svg"
        alt={compact ? "ReGuard" : ""}
      />
      {!compact && <span className="rg-brand-name">ReGuard</span>}
    </span>
  );
}
