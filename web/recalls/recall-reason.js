// Deterministic presentation of the official text. Never infer missing test values or health effects.
export function parseRecallReason(reason) {
  if (!reason?.trim()) return [];
  const blocks = [];
  let block = null;
  let previousField = null;
  for (const raw of reason.split(/\r?\n/)) {
    const line = raw.trim().replace(/^["“]|["”]$/g, "");
    if (!line) continue;
    const heading = line.match(/^[ㅇo○◦●•￮]\s*(.+)$/);
    if (heading || !block) {
      block = { title: heading ? heading[1] : line, fields: [], notes: [] };
      blocks.push(block);
      previousField = null;
      continue;
    }
    const field = line.match(
      /^[-–]?\s*(부위|측정값|기준치|검사결과|검사 결과|시험결과|시험 결과)\s*[:：]\s*(.*)$/,
    );
    if (field) {
      previousField = { label: field[1], value: field[2] };
      block.fields.push(previousField);
    } else if (previousField && !/^[-–]/.test(line)) {
      previousField.value += `\n${line}`;
    } else {
      block.notes.push(line.replace(/^[-–]\s*/, ""));
      previousField = null;
    }
  }
  return blocks.map((block) => ({ ...block, explanation: explain(block) }));
}
function explain({ title, fields }) {
  const standard =
    fields.find((field) => field.label === "기준치")?.value || "";
  if (/방부제.*검출/.test(title) && /사용되지\s*않을\s*것/.test(standard)) {
    return "이 제품에 사용할 수 없는 방부제가 검출됐어요.";
  }
  const exceeded = title.match(/^(.+?)\s*기준치?\s*(?:[\d.,]+\s*배\s*)?초과/);
  if (exceeded) return `${exceeded[1]} 수치가 허용 기준을 넘었어요.`;
  if (/^세균수\s*기준\s*(규격\s*)?부적합[.\s]*$/.test(title)) {
    return "세균 수 검사에서 정해진 기준을 충족하지 못했어요.";
  }
  if (/^대장균(?:군)?\s*기준\s*(규격\s*)?부적합[.\s]*$/.test(title)) {
    return `${title.startsWith("대장균군") ? "대장균군" : "대장균"} 검사에서 정해진 기준을 충족하지 못했어요.`;
  }
  return null;
}
export function reasonFieldLabel(label) {
  return (
    {
      부위: "검사한 부분",
      측정값: "검사 결과",
      기준치: "허용 기준",
      검사결과: "검사 결과",
      시험결과: "검사 결과",
      "시험 결과": "검사 결과",
    }[label] || label
  );
}

// List copy uses short noun phrases; measurements and explanatory sentences stay in detail.
export function conciseRecallReason(reason) {
  const issues = parseRecallReason(reason);
  if (!issues.length) return "사유 미제공";
  const labels = issues
    .map((issue) => {
      const label = conciseIssue(issue.title);
      return label === "상세 사유 확인 필요" ? sourceSummary(issue) : label;
    })
    .filter(Boolean);
  return [...new Set(labels)].join(" · ") || "사유 미제공";
}
// Unknown wording is quoted compactly, never replaced by an inferred health risk.
function sourceSummary(issue) {
  let text = issue.title
    .replace(/\((?:최중|중|경)?결함\)|<(?:최중|중|경)?결함>/g, "")
    .trim();
  if (!text || /^(?:불법\s*의심\s*내역|부적합\s*내용)$/.test(text))
    text = issue.notes.join(" ");
  text = text
    .replace(/^[ㅇo○◦●•￮\s:：-]+/, "")
    .replace(/\((?:최중|중|경)?결함\)/g, "")
    .replace(/(?:측정값|측정치|기준치|시험결과)\s*[:：].*$/, "")
    .replace(/[①-⑳]/g, "")
    .replace(
      /\d[\d.,~～\s]*\s*(?:mg\/kg|㎎\/㎏|kg|mm|cm|℃|%|배)(?:이하|이상)?/gi,
      "",
    )
    .replace(/\s+/g, " ")
    .trim();
  if (!text || /^(?:해당\s*없음|없음|없음\.|미제공|[-.\d\s]+)$/.test(text))
    return null;
  const classified = conciseIssue(text);
  if (classified !== "상세 사유 확인 필요") return classified;
  return text.length > 52 ? text.slice(0, 51).trimEnd() + "…" : text;
}
function conciseIssue(raw) {
  const text = raw.replace(/^[-–ㅇo○◦●•]\s*/, "").trim();
  if (
    /식품\s*원료/.test(text) &&
    /허용되지\s*않/.test(text) &&
    /부위.*포함/.test(text)
  )
    return "식품에 허용되지 않은 부위 포함";
  const clean = text.replace(/\((?:최중|중|경)?결함\)/g, "").trim();
  if (/수입/.test(text) && /무신고|신고하지|미신고/.test(text))
    return "수입 신고 없이 수입·판매";
  if (/무등록|영업등록을 하지/.test(text)) return "영업 등록 없이 제조·판매";
  if (/무신고\s*소분/.test(text)) return "신고 없이 소분·판매";
  if (/제조일자/.test(text) && /다르게|거짓|허위/.test(text))
    return "제조일자 허위 표시";
  if (/표시사항|표시 사항/.test(text) && /미비|누락|부적합|경결함/.test(text))
    return "제품 표시 미흡";
  if (/혼용[률율]/.test(text) && /오기|오류|부적합|위반/.test(text))
    return "섬유 혼용률 표시 오류";
  if (/이물/.test(text) && /혼입|검출/.test(text)) return "이물 혼입";
  if (/함량\s*부족/.test(text))
    return clean.replace(/\([^)]*\)/g, "").slice(0, 32);
  if (/3-MCPD/.test(text) && /초과|부적합/.test(text))
    return "3-MCPD 기준 초과";
  const chemicals = [
    ["납", "납"],
    ["카드뮴", "카드뮴"],
    ["폼알데하이드|포름알데히드", "폼알데하이드"],
    ["니켈", "니켈"],
    ["프탈레이트|가소제", "가소제"],
  ];
  for (const [pattern, label] of chemicals)
    if (new RegExp(pattern).test(text) && /초과|검출|용출/.test(text))
      return label + (/초과/.test(text) ? " 기준 초과" : " 검출");
  if (/기준.*미달/.test(clean)) return clean.replace(/기준.*$/, "기준 미달");
  if (/내부.*쇼트|내부.*단락/.test(text))
    return /배터리|전지/.test(text)
      ? "배터리 내부 단락 결함"
      : "내부 단락 결함";
  if (/온도\s*상승/.test(text) && /결함|부적합|초과|부품변경/.test(text))
    return "온도 상승 안전 기준 부적합";
  const named = [
    [/부품.*(?:임의)?변경|동일성.*부품변경/, "인증 당시와 다른 부품 사용"],
    [/부품.*누락|부품.*제거/, "부품 누락"],
    [/연면거리|공간거리|절연거리/, "절연거리 문제"],
    [/절연내력|전기적\s*강도/, "전기 절연 성능 문제"],
    [/충전부.*감전|감전.*보호|충전부.*노출/, "감전 보호 미흡"],
    [/접지/, "접지 설비 문제"],
    [/코드 및 조임끈/, "의류 조임끈 안전 문제"],
    [/전류파형|입력전류/, "입력 전류 기준 문제"],
    [/누전보호장치/, "누전 보호장치 문제"],
  ];
  for (const [pattern, label] of named) if (pattern.test(text)) return label;
  if (/방부제.*검출/.test(text)) return "방부제 검출";
  if (/배터리|전지/.test(text) && /과열|열폭주/.test(text)) {
    return /화재/.test(text) ? "배터리 과열·화재 위험" : "배터리 과열 위험";
  }
  if (/온도\s*상승/.test(text) && /초과|부적합/.test(text))
    return "온도 상승 안전 기준 부적합";
  const exceeded = text.match(
    /^(.+?)\s*기준(?:치)?\s*(?:[\d.,~～\s]+배\s*)?초과/,
  );
  if (exceeded && exceeded[1].length <= 24 && !/\d/.test(exceeded[1])) {
    return `${exceeded[1]
      .replace(/^총\s*/, "")
      .replace(/\s*함유량$/, "")
      .trim()} 기준 초과`;
  }
  const subjects = [
    [/세균수/, "세균 수"],
    [/대장균군/, "대장균군"],
    [/대장균/, "대장균"],
    [/세균발육/, "세균 발육"],
    [/잔류농약/, "잔류농약"],
    [/벤조피렌/, "벤조피렌"],
    [/아플라톡신/, "아플라톡신"],
    [/중금속/, "중금속"],
    [/붕해시험/, "붕해 시험"],
    [/금속성?\s*이물/, "금속 이물"],
    [/프탈레이트/, "프탈레이트"],
  ];
  for (const [pattern, label] of subjects) {
    if (pattern.test(text) && /부적합|초과|검출/.test(text)) {
      return `${label} ${/초과/.test(text) ? "기준 초과" : /부적합/.test(text) ? "기준 부적합" : "검출"}`;
    }
  }
  if (/소비기한|유통기한/.test(text) && /표시|변조|변경/.test(text))
    return "소비·유통기한 표시 문제";
  if (/식품첨가물/.test(text) && /위반|부적합/.test(text))
    return "식품첨가물 사용 기준 위반";
  if (/표시/.test(text) && /미흡|누락|미표시|오류|위반|부적합/.test(text))
    return "제품 표시 기준 부적합";
  if (/감전/.test(text) && /위험|우려|가능/.test(text)) return "감전 위험";
  if (/질식/.test(text) && /위험|우려|가능/.test(text)) return "질식 위험";
  if (/화재/.test(text) && /위험|우려|발생|가능/.test(text)) return "화재 위험";
  if (/화상/.test(text) && /위험|우려|발생|가능/.test(text)) return "화상 위험";
  // Keep a short existing nominal heading, stripping numerical comparisons and technical parentheses.
  const compact = text
    .replace(/\([^)]*\)/g, "")
    .replace(/[\d.,]+\s*배\s*/g, "")
    .replace(/기준\s*규격/g, "기준")
    .replace(/\s+/g, " ")
    .replace(/[.。]$/, "")
    .trim();
  if (
    compact.length <= 32 &&
    !/\d|mg\/|kg|℃|%/.test(compact) &&
    /(?:초과|부적합|위반|검출|결함|불량|누락|위험)$/.test(compact)
  )
    return compact;
  if (/기준.*부적합|안전.*부적합/.test(text)) return "안전 기준 부적합";
  return "상세 사유 확인 필요";
}
