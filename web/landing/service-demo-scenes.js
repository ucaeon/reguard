const searchFrame = (file, duration, caption, cursor = null) => ({
  file,
  duration,
  caption,
  cursor,
  width: 1052,
  height: 630,
});
const manualFrame = (file, duration, caption, cursor = null, height = 730) => ({
  file,
  duration,
  caption,
  cursor,
  width: 700,
  height,
});
export const captures = {
  "search-empty": searchFrame(
    "search-empty",
    250,
    "제품 검색창에 제품명을 입력해요.",
  ),
  "search-type-1": searchFrame(
    "search-type-1",
    140,
    "제품 검색창에 제품명을 입력해요.",
  ),
  "search-type-2": searchFrame(
    "search-type-2",
    160,
    "제품 검색창에 제품명을 입력해요.",
  ),
  "search-type-3": searchFrame(
    "search-type-3",
    180,
    "제품 검색창에 제품명을 입력해요.",
  ),
  "search-type-4": searchFrame(
    "search-type-4",
    650,
    "검색 버튼을 눌러요.",
    [970, 150],
  ),
  search: searchFrame("search", 1600, "검색된 제품 목록을 확인해요."),
  "product-entry": searchFrame(
    "search",
    800,
    "검색 결과에서 해당 제품을 선택해요.",
    [145, 385],
  ),
  "product-scroll": {
    file: "product",
    width: 620,
    height: 470,
    imageHeight: 733,
    duration: 3600,
    caption: "상세 정보를 내려보며 모델명과 인증번호를 확인해요.",
  },
  "manual-empty": manualFrame(
    "manual-empty",
    450,
    "직접 등록 화면에서 제품 종류를 선택해요.",
  ),
  "manual-name": manualFrame(
    "manual-name",
    650,
    "포장에 적힌 제품명을 입력해요.",
  ),
  "manual-company": manualFrame(
    "manual-company",
    700,
    "제조·수입업체명을 입력해요.",
  ),
  "manual-submit": manualFrame(
    "manual-submit",
    1000,
    "인증번호를 입력하고 내 물건에 등록해요.",
    [590, 700],
    760,
  ),
  "manual-complete": manualFrame(
    "manual-complete",
    1600,
    "입력한 정보가 저장되고 등록이 완료돼요.",
  ),
  "recall-list": {
    file: "recall-list",
    width: 1052,
    height: 730,
    duration: 1000,
    cursor: [300, 340],
    caption: "리콜 목록에서 허니 슬라임을 선택해요.",
  },
  "recall-flow": {
    file: "recall-flow",
    width: 1052,
    height: 730,
    imageHeight: 960,
    duration: 4500,
    caption: "상세 페이지를 내려보며 리콜 이유와 검사 결과를 확인해요.",
  },
  alerts: {
    width: 1052,
    height: 630,
    caption: "내 물건과 관련된 리콜 소식을 알림함에서 확인해요.",
  },
};
export const scenes = {
  search: [
    "search-empty",
    "search-type-1",
    "search-type-2",
    "search-type-3",
    "search-type-4",
    "search",
  ],
  product: ["product-entry", "product-scroll"],
  registered: [
    "manual-empty",
    "manual-name",
    "manual-company",
    "manual-submit",
    "manual-complete",
  ],
  recall: ["recall-list", "recall-flow"],
  alerts: ["alerts"],
};
