export function apiRequest(path, options = {}, transport = globalThis.fetch) {
  if (typeof path !== "string" || !path.startsWith("/api/v1/")) {
    throw new TypeError(
      "API 요청은 동일 출처의 /api/v1/ 경로를 사용해야 합니다.",
    );
  }
  return transport(path, {
    credentials: "include",
    cache: "no-store",
    ...options,
  });
}

/** Tokens are deliberately not cached across login/logout or service boundaries. */
export async function getCsrf(
  path = "/api/v1/auth/csrf",
  message = "서버에 연결하지 못했어요. 다시 시도해 주세요.",
  request = apiRequest,
) {
  const response = await request(path, {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  const token = await response.json();
  if (!token?.headerName || !token?.token) throw new Error(message);
  return token;
}

export async function requestJson(
  path,
  options = {},
  policy = {},
  request = apiRequest,
) {
  const response = await request(path, {
    credentials: "include",
    cache: "no-store",
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(
      policy.statusMessages?.[response.status] ||
        (policy.serverMessage && data.message) ||
        policy.message ||
        "요청을 처리하지 못했어요. 다시 시도해 주세요.",
    );
    error.status = response.status;
    error.code = data.code;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
export async function mutateJson(
  path,
  method,
  body,
  policy = {},
  request = apiRequest,
) {
  const csrf = await getCsrf(
    policy.csrfPath || "/api/v1/auth/csrf",
    policy.message,
    request,
  );
  return requestJson(
    path,
    {
      method,
      headers: {
        "Content-Type": "application/json",
        [csrf.headerName]: csrf.token,
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
    policy,
    request,
  );
}
