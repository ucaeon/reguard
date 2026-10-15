<p align="center">
  <img src="web/public/brand/reguard-mark.svg" width="80" alt="ReGuard 딥틸 로고" />
</p>
<p align="center"><strong>매일 쓰는 물건 계속 써도 괜찮을까?</strong><br />내 물건과 관련된 리콜 정보를 한곳에서.</p>

<p align="center">
  <img src="assets/readme/home-scroll.gif" width="1000" alt="ReGuard 메인페이지 스크롤 데모" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Java-21-ED8B00?style=flat-square" alt="Java 21" />
  <img src="https://img.shields.io/badge/Spring_Boot-3.5-6DB33F?style=flat-square&amp;logo=springboot&amp;logoColor=white" alt="Spring Boot" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/React-19-149ECA?style=flat-square&amp;logo=react&amp;logoColor=white" alt="React" />
  <br />
  <img src="https://img.shields.io/badge/Apache_Kafka-3.9-231F20?style=flat-square&amp;logo=apachekafka&amp;logoColor=white" alt="Kafka" />
  <img src="https://img.shields.io/badge/Apache_Spark-4.0-E25A1C?style=flat-square&amp;logo=apachespark&amp;logoColor=white" alt="Spark" />
  <img src="https://img.shields.io/badge/Airflow-DAG-017CEE?style=flat-square&amp;logo=apacheairflow&amp;logoColor=white" alt="Airflow" />
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&amp;logo=postgresql&amp;logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&amp;logo=docker&amp;logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/k3s-Local-FFC61C?style=flat-square&amp;logo=k3s&amp;logoColor=black" alt="Local k3s" />
</p>

<p align="center">
  <a href="#overview">Overview</a> · <a href="#architecture">Architecture</a> · <a href="#quick-start">Quick Start</a> · <a href="#verification">Verification</a>
</p>

<br />

## Overview

ReGuard는 식품안전나라와 Safety Korea의 제품·리콜 데이터를 통합해 등록한 물건의 리콜 소식을 알려주는 서비스입니다.

수집 → 정규화 → 제품 식별 → 리콜 매칭 → 알림으로 이어집니다. 재처리 시 중복 반영을 막고 제품 정보가 바뀌면 기존 매칭을 갱신합니다.

| 제품 검색·등록 | 리콜 정보 확인 | 내 물건 알림 |
|:---:|:---:|:---:|
| 제품명·식별자로 검색하고 직접 등록 | 리콜 사유·대상 조건·조치 방법 확인 | 등록 물건의 관련 리콜과 변경 소식 확인 |
| 등록 정보 수정·삭제 | 확정 매칭과 후보 구분 | 읽음 처리·미확인 개수·수신 설정 |

<br />

## Architecture

<p align="center">
  <img src="assets/readme/architecture.png" width="1000" alt="ReGuard 구조: 공공 API → Airflow·Python → Kafka → Spark → Safety DB. React·Caddy를 통한 서비스별 요청과 Outbox·Kafka를 통한 알림 전달." />
</p>

배포 구성에서는 React 웹의 요청을 Caddy가 담당 서비스로 전달합니다. 아래 개발 실행 절차에서는 Vite 프록시가 같은 역할을 합니다. 수집 데이터는 Kafka와 Spark를 거쳐 Safety DB에 저장됩니다.

Member는 Safety API로 보유 제품의 리콜을 확인합니다. Outbox에 기록한 이벤트는 Kafka를 거쳐 Notification으로 전달됩니다. 그림의 Outbox → Kafka는 Member의 이벤트 발행 경로입니다. 두 Kafka 상자는 같은 브로커의 서로 다른 토픽입니다.

| 흐름 | 책임 | 구현 |
|---|---|---|
| **수집·스케줄링** | 기관별 수집·원본 보존·재시도·완료 확인 | [Collectors](pipelines/collectors/) · [Airflow](orchestration/airflow/) |
| **정규화·저장** | 이벤트 검증·중복 및 과거 버전 처리·저장·매칭 | [Spark pipeline](pipelines/spark/) |
| **서비스 API** | 회원·보유제품 / 제품·리콜 / 알림의 책임과 DB 소유권 분리 | [Member](services/member-service/) · [Safety](services/safety-service/) · [Notification](services/notification-service/) |
| **알림 전달** | Safety API 조회 → Outbox 기록 → Kafka → Notification | [Scanner](services/member-service/src/main/java/dev/reguard/member/alerts/RecallAlertScanner.java) · [Producer](services/member-service/src/main/java/dev/reguard/member/alerts/RecallAlertProducer.java) |
| **웹·실행 환경** | React 화면·Caddy 라우팅·로컬 k3s·영속 볼륨 | [Web](web/) · [Caddy](infra/runtime/Caddyfile) · [Release](infra/release/) |

단일 노드 로컬 k3s에서 실행합니다. 서비스별 DB는 논리적으로 분리되어 있습니다. 서버 장애 격리와 고가용성은 지원하지 않습니다.

<br />

## Quick Start

**필수 환경:** JDK 21 · Python 3.12 · uv · Node.js 22.22.2+ (22.x) 또는 24.15.0+ (24.x) · Docker Compose

모든 명령은 저장소 루트에서 실행합니다. Docker 엔진을 먼저 시작합니다. 이 절차는 Compose DB와 로컬 Java·Vite를 사용하며 k3s를 설치하지 않습니다.

`.env`를 만든 뒤 아래 값을 입력합니다. 기존 파일은 유지합니다.

| 설정 | 용도 |
|---|---|
| `POSTGRES_PASSWORD` · `MEMBER_DB_PASSWORD` · `SAFETY_DB_PASSWORD` · `NOTIFICATION_DB_PASSWORD` | DB 초기화와 서비스 연결에 필수 |
| `MAIL_ENABLED=true` · `MAIL_FROM` · `SMTP_*` | 회원가입 인증 메일과 비밀번호 재설정 |
| `FOOD_SAFETY_API_KEY` · `SAFETY_KOREA_API_KEY` | 수집 파이프라인 실행에 필수 |

메일 설정이 없으면 회원가입 인증 메일을 보낼 수 없습니다. DB 비밀번호는 최초 초기화 때 적용됩니다. 기존 DB의 비밀번호는 `.env` 수정만으로 바뀌지 않습니다.

```bash
test -f .env || cp .env.example .env
# .env 값을 입력한 뒤 다음 명령 실행
uv sync --frozen
npm --prefix web ci

docker compose --env-file .env -f infra/compose/compose.yml up -d --wait
./mvnw -B -ntp package
```

각각 별도 터미널에서 실행합니다.

```bash
./scripts/run-service.sh member        # 8081
./scripts/run-service.sh safety        # 8082
./scripts/run-service.sh notification  # 8083
npm --prefix web run dev               # http://localhost:3000
```

브라우저에서 `http://localhost:3000`으로 접속합니다. 기존 프로세스가 3000·8081~8083·15432 포트를 사용 중이면 먼저 포트 충돌을 해결합니다.

빈 DB에는 제품·리콜이 없습니다. 아래 수집 절차는 증분 수집이며 과거 전체 데이터를 자동 적재하지 않습니다. 초기 전체 적재는 아래 절차를 따릅니다.

<details>
<summary><strong>빈 DB에 초기 데이터 적재</strong></summary>

저장소 루트에서 실행합니다. 앞 단계의 PostgreSQL과 Safety 서비스를 먼저 실행해 DB 스키마를 생성합니다. `.env`에 DB 비밀번호와 두 기관 API 키를 입력합니다. 초기 적재 중에는 Airflow 수집과 Spark를 실행하지 않습니다. 이미 실행 중이면 진행 중인 수집이 끝난 뒤 `bash scripts/airflow.sh stop`으로 중지합니다.

이 절차는 공식 전체 파일을 DB에 직접 적재합니다. 이후 변경분은 위의 Kafka·Spark 수집 절차로 반영합니다. 기관이 제공하는 현재 전체 파일 범위이며 삭제된 과거 자료까지 복원하지는 않습니다.

**1. 식품 전체 파일 다운로드**

일반식품 `I1250` · 건강기능식품 `I0030` · 식품 리콜 `I0490`의 파일 API 사용 권한이 필요합니다. 기존 다운로드 함수로 파일 형식·해시·최신성을 검사합니다.

```bash
uv run python - <<'PY'
from pathlib import Path
import gzip
import os
import shutil
import httpx
from dotenv import dotenv_values
from pipelines.collectors.food_snapshot import download

env = {**dotenv_values('.env'), **os.environ}
key = env.get('FOOD_SAFETY_API_KEY')
if not key:
    raise SystemExit('FOOD_SAFETY_API_KEY 설정 필요')
root = Path('data/food-bootstrap')
for service, filename in [
    ('I1250', '일반식품검색.csv'),
    ('I0030', '건강기능식품검색.csv'),
    ('I0490', '식품리콜알림.csv'),
]:
    directory = root / service
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(600, connect=15)) as client:
        archive, _ = download(directory, service, key, client)
    with gzip.open(archive, 'rb') as source, (directory / filename).open('wb') as target:
        shutil.copyfileobj(source, target)
    print(service, '다운로드 완료')
PY
```

**2. 식품 적재 후 리콜 매칭**

```bash
uv run python scripts/import_food_csv.py --data-dir data/food-bootstrap
uv run python scripts/match_food_recalls.py
```

기본 DB 컨테이너 이름은 `reguard-local-postgres-1`입니다. 이름을 변경했다면 두 명령에 `--container 실제컨테이너이름`을 추가합니다. 결과는 `data/import-reports/`의 실행별 `report.json`에 저장됩니다. `rejected`가 있으면 같은 폴더의 거절 기록을 확인합니다. 명령 종료만으로 전체 행 적재 성공을 판단하지 않습니다.

**3. KC 제품과 리콜 적재**

```bash
uv run python -m pipelines.bootstrap.kc download --directory data/kc-bootstrap
uv run python -m pipelines.bootstrap.kc load-products --directory data/kc-bootstrap
uv run python -m pipelines.bootstrap.kc load-recalls --directory data/kc-bootstrap
```

제품을 먼저 적재합니다. `load-recalls`는 리콜 적재와 KC 매칭을 함께 수행합니다. `data/kc-bootstrap/products-report.json`과 `recalls-report.json`의 `status`가 `complete`인지 확인하고 거절 건수와 기록도 확인합니다. 다운로드 명령은 같은 폴더의 기존 파일을 재사용합니다. 새 스냅샷이 필요하면 세 명령 모두 새로운 `--directory`를 지정합니다.

**4. 저장 건수와 화면 확인**

```bash
docker compose --env-file .env -f infra/compose/compose.yml exec -T postgres \
  psql -X -v ON_ERROR_STOP=1 -U reguard_safety -d reguard_safety <<'SQL'
SELECT source, count(*) FROM products GROUP BY source ORDER BY source;
SELECT source, count(*) FROM recalls GROUP BY source ORDER BY source;
SELECT count(*) AS matches FROM recall_product_matches;
SQL
```

적재 보고서와 DB 건수를 대조한 뒤 `http://localhost:3000/?view=recalls`에서 목록과 상세 내용을 확인합니다. 매칭 건수는 원천 데이터와 규칙에 따라 달라집니다. 확인 후 수집 파이프라인을 시작합니다. 초기 적재는 사용자 물건이나 알림을 생성하지 않습니다.

</details>

<details>
<summary><strong>수집 파이프라인 실행</strong></summary>

```bash
docker compose -f infra/compose/kafka.yml up -d --wait
for topic in reguard.raw-records.v1 reguard.recall-alerts.v1; do
  docker compose -f infra/compose/kafka.yml exec -T kafka \
    /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
    --create --if-not-exists --topic "$topic" --partitions 1 --replication-factor 1
done
bash scripts/airflow.sh up
```

앞 단계의 DB와 세 Java 서비스를 실행한 상태에서 진행합니다. `airflow.sh up`은 Airflow와 Spark를 빌드하고 시작합니다. 최초 실행에는 이미지·의존성 다운로드가 필요합니다.

Airflow는 `http://localhost:18080`에서 확인합니다. 로컬 계정은 `admin`입니다. 초기 비밀번호는 아래 명령으로 확인합니다.

```bash
docker compose --env-file .env -f orchestration/airflow/compose.yml \
  exec -T api-server cat /opt/airflow/state/ui-passwords.json
```

수집 DAG는 기본적으로 일시 중지되어 있습니다. 예를 들어 `reguard_food_recalls`를 활성화하고 실행한 뒤 `wait_for_database`와 `complete` 성공을 확인합니다. `reguard_recall_images`는 기본 활성화되어 15분마다 실행됩니다. 기관 API 호출 한도를 확인하고 필요한 DAG만 활성화합니다.

새 알림을 생성하려면 `.env`에서 `ALERTS_ENABLED=true`를 설정하고 Member와 Notification을 재시작합니다. 기본 Kafka 주소는 `127.0.0.1:19092`입니다. 사용자 수신 설정과 등록 물건에 연결된 리콜도 필요합니다.

[환경 변수](.env.example) · [Airflow DAG](orchestration/airflow/dags/reguard.py) · [수집 실행](orchestration/airflow/execution.py)

</details>

<br />

## Verification

외부 API 호출이나 서비스 DB 변경 없이 수행하는 검사:

```bash
uv run python scripts/check.py --suite all
```

Spark 장애 복구 검증에는 Docker 환경과 `reguard-spark:portable-20261015.2` 런타임 이미지가 필요합니다. 이미지가 없으면 다음 명령으로 테스트에 필요한 Spark 이미지만 빌드합니다. 베이스 이미지는 [고정 버전 목록](infra/release/bases.json)을 사용합니다. 현재 릴리스 대상은 Linux ARM64입니다. 다른 아키텍처에서는 에뮬레이션이 필요할 수 있습니다. 검증 도구는 별도 Kafka·PostgreSQL·Spark 컨테이너를 생성하고 종료 후 정리합니다.

```bash
docker build --platform linux/arm64 -f infra/release/Spark.Dockerfile \
  --build-arg JRE="$(uv run python -c 'import json; print(json.load(open("infra/release/bases.json"))["JRE"])')" \
  --build-arg PYTHON="$(uv run python -c 'import json; print(json.load(open("infra/release/bases.json"))["PYTHON"])')" \
  -t reguard-spark:portable-20261015.2 .
uv run python scripts/verify_spark_crash_recovery.py
```

| 범위 | 확인된 상태 |
|---|---|
| 서비스 | 로그인·물건 CRUD·프로필·알림 구현 |
| 데이터 정합성 | 커밋 경계 종료·체크포인트 복구·증분 매칭 검증 |
| 실행·복구 | 별도 로컬 k3s 환경 설치 및 백업 복원 검증 |
| AWS | 배포 준비 코드 포함 · **배포·운영 미실시** |

공개 검증 결과는 `assets/readme/verification/`에 보관합니다. 개인 문서·인증정보·원본 데이터·백업·런타임 로그는 Git에서 제외합니다.

<br />

## Project Structure

```text
services/         회원·안전 정보·알림 Spring Boot 서비스
pipelines/        기관별 수집·정규화·저장·매칭
orchestration/    Airflow DAG와 수집·품질 검사 조율
web/              React 웹 애플리케이션
infra/            Compose·k3s·릴리스 및 AWS 준비 설정
scripts/          실행·설치·복구 도구와 통합 검증
assets/readme/    공개 데모·아키텍처·검증 결과
```

데이터 출처: **식품안전나라 · Safety Korea**. 제품·리콜 원문은 공공기관 정보를 따릅니다. 후보 매칭은 대상 조건을 추가로 확인해야 합니다.
