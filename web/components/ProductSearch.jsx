import React from "react";

export default function ProductSearch({
  value,
  onChange,
  onSearch,
  large = false,
  required = true,
  placeholder = "제품명 · 업체명 · 인증번호",
}) {
  return (
    <form
      className={"search " + (large ? "large" : "")}
      onSubmit={(e) => {
        e.preventDefault();
        onSearch();
      }}
    >
      <span aria-hidden="true">⌕</span>
      <input
        aria-label="제품 검색어"
        maxLength={100}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
      />
      <button type="submit">
        검색<span aria-hidden="true"> →</span>
      </button>
    </form>
  );
}
