import { conciseRecallReason } from "./recalls/recall-reason.js";
const labels = {
  MNFDT: "제조일자",
  DISTBTMLMT: "소비·유통기한",
  FRMLCUNIT: "포장 단위",
  recallModelName: "제품명",
  modelName: "모델명",
  modelNm: "모델명",
  model: "모델명",
  manufactureDate: "제조일자",
  expirationDate: "소비기한",
  lotNumber: "제조번호",
  batchNumber: "제조번호",
  certNum: "인증번호",
  certificationNumber: "인증번호",
};

export function conditionText(value) {
  if (value == null || value === "")
    return "대상 조건이 제공되지 않았습니다. 기관 원문을 확인해주세요.";
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      return value;
    }
  }
  if (parsed == null) return conditionText(null);
  if (typeof parsed !== "object") return String(parsed);
  const entries = Array.isArray(parsed)
    ? parsed.map((v) => ["", v])
    : Object.entries(parsed);
  const lines = entries
    .filter(([, v]) => v != null && v !== "")
    .map(([key, v]) => {
      const text = typeof v === "object" ? conditionText(v) : String(v);
      const prefix = text.match(/^\((제조일자|소비기한|유통기한)\)/)?.[1];
      const label =
        prefix ||
        labels[key] ||
        (/[가-힣]/.test(key) ? key : `기타 조건 (${key})`);
      const clean = text.replace(/^\((제조일자|소비기한|유통기한)\)\s*/, "");
      return key ? `${label}: ${clean}` : clean;
    });
  return lines.length ? lines.join("\n") : conditionText(null);
}

export function identifierLabel(type) {
  return (
    {
      KC_CERT_NO: "KC 인증번호",
      BARCODE: "바코드",
      FOOD_REPORT_NO: "품목보고번호",
    }[type] || "제품 식별번호"
  );
}

export function recallName(item) {
  let conditions = item?.targetConditions;
  try {
    if (typeof conditions === "string") conditions = JSON.parse(conditions);
  } catch {
    conditions = null;
  }
  const model = conditions?.recallModelName;
  if (typeof model === "string" && model.trim())
    return model.replace(/^\s*\(제품명\)\s*/, "").trim();
  return item?.productName || item?.name || "제품명 미제공";
}
export function recallSummary(reason) {
  return conciseRecallReason(reason);
}

export function recallFallback(item) {
  const text = [recallName(item), item?.productName, item?.reason].join(" ");
  return `/images/recall-${/슬라임|액체괴물/i.test(text) ? "slime" : item?.source === "FOOD_I0490" ? "food" : "toy"}.svg`;
}

export function verifiedRecallPhotos(item) {
  let conditions = item?.targetConditions;
  try {
    if (typeof conditions === "string") conditions = JSON.parse(conditions);
  } catch {
    return [];
  }
  return conditions?.certNum === "CB065R2649-4001" &&
    item?.companyName?.trim() === "리틀아이" &&
    recallName(item).includes("허니")
    ? [
        "https://office.safetykorea.kr/fileData/2026_%EC%96%B4%EB%A6%B0%EC%9D%B4%EC%A0%9C%ED%92%88_%EC%88%98%EC%8B%9C%202%EC%B0%A8%28%EC%B4%89%EA%B0%90%20%EC%9E%A5%EB%82%9C%EA%B0%90%29/03/202609/2026-9-10-19-48-34_%EC%A0%84%EC%B2%B4_%282%29.png",
        "https://office.safetykorea.kr/fileData/2026_%EC%96%B4%EB%A6%B0%EC%9D%B4%EC%A0%9C%ED%92%88_%EC%88%98%EC%8B%9C%202%EC%B0%A8%28%EC%B4%89%EA%B0%90%20%EC%9E%A5%EB%82%9C%EA%B0%90%29/04/202609/2026-9-10-19-48-34_%EB%B6%80%EB%B6%84_%282%29.PNG",
      ]
    : [];
}
