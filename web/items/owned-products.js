import { apiRequest, mutateJson } from "../lib/api-client.js";
export async function loadOwnedProducts(signal, request = apiRequest) {
  const items = [];
  for (let page = 0; ; page++) {
    const response = await request(
      `/api/v1/me/products?page=${page}&size=100`,
      { credentials: "include", cache: "no-store", signal },
    );
    if (!response.ok) {
      const error = new Error(
        response.status === 401
          ? "로그인하고 등록한 물건을 확인하세요."
          : "물건을 불러오지 못했어요. 다시 시도해 주세요.",
      );
      error.status = response.status;
      throw error;
    }
    const data = await response.json();
    items.push(...data.items);
    if (!data.hasNext) return items;
  }
}
export function ownedCategory(item) {
  return item.identifierType === "FOOD_REPORT_NO"
    ? "식품"
    : item.identifierType === "KC_CERT_NO"
      ? "생활용품·어린이 제품"
      : "미분류";
}
export function ownedEditPayload(item, values) {
  const fields =
    item.registrationType === "CATALOG"
      ? ["expiryDate", "lotNumber"]
      : [
          "productName",
          "companyName",
          "modelName",
          "identifierType",
          "identifierValue",
          "expiryDate",
          "lotNumber",
        ];
  const body = Object.fromEntries(
    fields.map((key) => [key, values[key]?.trim() || null]),
  );
  if (item.registrationType !== "CATALOG") {
    if (!body.productName) throw new Error("제품명을 입력해 주세요.");
    if (!body.identifierValue) body.identifierType = null;
    if (body.identifierValue && !body.identifierType)
      throw new Error("식별번호 종류를 선택해 주세요.");
  }
  return body;
}
export async function changeOwnedProduct(
  id,
  method,
  body,
  request = apiRequest,
) {
  return mutateJson(
    `/api/v1/me/products/${encodeURIComponent(id)}`,
    method,
    body,
    {
      serverMessage: true,
      message: "변경하지 못했어요. 다시 시도해 주세요.",
      statusMessages: {
        401: "로그인이 만료됐어요. 다시 로그인해 주세요.",
        404: "이미 삭제됐거나 찾을 수 없는 물건이에요. 목록을 새로고침해 주세요.",
      },
    },
    request,
  );
}

export function ownedRecallLinks(result) {
  return (result?.items || [])
    .map((match) => match.recall)
    .filter((recall) => recall?.id);
}
