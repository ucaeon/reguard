import test from "node:test";
import assert from "node:assert/strict";
import { parseRecallReason } from "./recalls/recall-reason.js";
test("preserves both issues and exact measurements including wrapped text", () => {
  const text =
    "ㅇ 방부제(MIT, CMIT, MIT+CMIT) 검출됨\n- 부위: 슬라임(하양)\n- 측정값: MIT 0.38 mg/kg, CMIT 1.42 mg/kg, MIT+CMIT 2\nmg/kg\n- 기준치: 사용되지 않을 것(MIT, CMIT, MIT+CMIT)\n\nㅇ 붕소 기준치 4.7배 초과\n- 측정값: 1 399 mg/kg\n- 기준치: 300 mg/kg 이하";
  const blocks = parseRecallReason(text);
  assert.equal(blocks.length, 2);
  assert.equal(
    blocks[0].explanation,
    "이 제품에 사용할 수 없는 방부제가 검출됐어요.",
  );
  assert.equal(
    blocks[0].fields[1].value,
    "MIT 0.38 mg/kg, CMIT 1.42 mg/kg, MIT+CMIT 2\nmg/kg",
  );
  assert.equal(blocks[1].fields[0].value, "1 399 mg/kg");
  assert.equal(blocks[1].explanation, "붕소 수치가 허용 기준을 넘었어요.");
});
test("does not invent measurements or a prohibition", () => {
  const [food] = parseRecallReason("세균수 기준 규격 부적합");
  assert.equal(food.fields.length, 0);
  assert.match(food.explanation, /기준을 충족하지 못했어요/);
  assert.equal(parseRecallReason("방부제 검출됨")[0].explanation, null);
});
test("unrecognized reasons and extra details are preserved", () => {
  const [block] = parseRecallReason("포장 표시 오류\n- 별도 확인 사항");
  assert.equal(block.title, "포장 표시 오류");
  assert.deepEqual(block.notes, ["별도 확인 사항"]);
  assert.equal(block.explanation, null);
  assert.deepEqual(parseRecallReason(null), []);
});

import { conciseRecallReason } from "./recalls/recall-reason.js";
test("list reasons are short noun phrases without measurements", () => {
  const samples = [
    [
      "ㅇ 방부제(MIT, CMIT, MIT+CMIT) 검출됨\n- 측정값: MIT 0.38 mg/kg\nㅇ 붕소 기준치 4.7배 초과",
      "방부제 검출 · 붕소 기준 초과",
    ],
    [
      "스피커 내부의 리튬 이온 배터리가 과열되어 열폭주 현상이 발생, 화재 또는 연기 발생하거나 고온의 배터리 물질 등이 분출될 수 있음",
      "배터리 과열·화재 위험",
    ],
    [
      "- 사후 관리(정기 심사)결과, 온도 상승 시험(135.4K) 및 정상 동작 시험(71.5K) 기준(45K이하) 초과에 따른 안전 기준 부적합",
      "온도 상승 안전 기준 부적합",
    ],
    ["총 납 함유량 기준치 167.8배 초과", "납 기준 초과"],
    ["세균수 기준 규격 부적합", "세균 수 기준 부적합"],
  ];
  for (const [input, output] of samples)
    assert.equal(conciseRecallReason(input), output);
});
test("unknown prose does not invent a hazard or expose measurements", () => {
  assert.equal(
    conciseRecallReason("추가 조사가 필요한 사유로 제품을 회수합니다."),
    "추가 조사가 필요한 사유로 제품을 회수합니다.",
  );
  assert.equal(
    conciseRecallReason("대장균 기준 규격 부적합"),
    "대장균 기준 부적합",
  );
});

test("unapproved food plant parts are summarized without inventing a hazard", () => {
  assert.equal(
    conciseRecallReason("식품원료로 허용되지 않는 부위(껍질,쥬스,라텍스) 포함"),
    "식품에 허용되지 않은 부위 포함",
  );
});

test("handles missing bullet spacing and common source wording", () => {
  assert.equal(
    conciseRecallReason(
      "ㅇ총 납 함유량 기준치 4.8배 초과\n-측정값:487 mg/kg\nㅇ 표시사항 미비",
    ),
    "납 기준 초과 · 제품 표시 미흡",
  );
  assert.equal(
    conciseRecallReason("식약처에 수입신고하지 아니한 식품을 수입·판매"),
    "수입 신고 없이 수입·판매",
  );
  assert.equal(
    conciseRecallReason("제조일자 사실과 다르게 표시"),
    "제조일자 허위 표시",
  );
  assert.equal(conciseRecallReason("3-MCPD 기준 초과"), "3-MCPD 기준 초과");
  assert.equal(
    conciseRecallReason("○ (최중결함)\n- 충전부 노출"),
    "감전 보호 미흡",
  );
  assert.equal(conciseRecallReason("11"), "사유 미제공");
  assert.equal(conciseRecallReason(null), "사유 미제공");
});
