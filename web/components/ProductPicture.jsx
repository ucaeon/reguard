import React, { useEffect, useState } from "react";
import { safeUrl } from "../lib/safe-url.js";

export default function ProductPicture({ url, name, fallback }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return safeUrl(url) && !failed ? (
    <img
      loading="lazy"
      src={safeUrl(url)}
      alt={name}
      onError={() => setFailed(true)}
    />
  ) : fallback ? (
    <img src={fallback} alt={`${name} 카테고리 기본 이미지`} />
  ) : (
    <div className="placeholder">
      <span>◇</span>
      <small>이미지 없음</small>
    </div>
  );
}
