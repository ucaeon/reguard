import { requestJson } from "./api-client.js";
export function catalogApi(path, options = {}) {
  return requestJson("/api/v1" + path, options, {
    message: "정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
    statusMessages: {
      503: "데이터 연결이 잠시 원활하지 않아요. 다시 시도해주세요.",
    },
  });
}
