from datetime import timedelta

import pendulum
from airflow.exceptions import AirflowFailException
from airflow.providers.standard.sensors.python import PythonSensor
from airflow.sdk import Param, dag, get_current_context, task

SOURCES = [
    "food-products",
    "food-supplements",
    "food-recalls",
    "kc-products",
    "safety-recalls",
]
DEFAULTS = {
    "owner": "reguard",
    "retries": 2,
    "retry_delay": timedelta(hours=1),
    "execution_timeout": timedelta(hours=2),
}


def database_applied(path):
    from orchestration.airflow.jobs import applied_plan

    return applied_plan(path) if path else True


def pipeline(dag_id, source, schedule, mode="incremental", manual=False):
    params = {}
    if manual:
        params = {
            "source": Param(
                source,
                enum=[
                    s
                    for s in SOURCES
                    if s.startswith("food-") == source.startswith("food-")
                ],
            ),
            "start_day": Param(None, type=["null", "string"], format="date"),
            "end_day": Param(None, type=["null", "string"], format="date"),
        }

    @dag(
        dag_id=dag_id,
        schedule=schedule,
        start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Seoul"),
        catchup=False,
        max_active_runs=1,
        dagrun_timeout=timedelta(hours=8),
        default_args=DEFAULTS,
        params=params,
        tags=["reguard", "ingestion"],
        description="공공 API 수집 → Kafka → Spark DB 반영 확인. 전체 초기 적재와 분리.",
    )
    def definition():
        @task(task_id="plan", retries=0)
        def make_plan():
            from orchestration.airflow.jobs import plan

            context = get_current_context()
            selected = context["params"]["source"] if manual else source
            end = (
                context["params"]["end_day"]
                if manual
                else (context.get("data_interval_end") or pendulum.now("Asia/Seoul"))
                .in_timezone("Asia/Seoul")
                .date()
                .isoformat()
            )
            start = context["params"]["start_day"] if manual else None
            if manual and (not start or not end):
                raise AirflowFailException(
                    "수동 재수집은 시작일과 종료일을 입력해야 합니다."
                )
            try:
                return plan(
                    selected,
                    "backfill" if manual else mode,
                    dag_id + ":" + context["run_id"],
                    end_day=end,
                    start_day=start,
                )
            except ValueError as error:
                raise AirflowFailException(str(error)) from None

        @task(
            task_id="collect",
            pool="food_api" if source.startswith("food-") else "safety_api",
        )
        def collect_source(path):
            from orchestration.airflow.jobs import collect_plan
            from pipelines.collectors.common import CollectionError

            try:
                return collect_plan(path)
            except CollectionError as error:
                if str(error) in {
                    "INFO-100",
                    "INFO-110",
                    "INFO-120",
                    "INFO-400",
                    "INFO-600",
                    "SAFETY_4000",
                    "SAFETY_4001",
                    "SAFETY_DAILY_LIMIT_REACHED",
                    "FOOD_GAP_REQUIRES_SNAPSHOT_RECOVERY",
                    "MISSING_PROVIDER_KEY",
                }:
                    raise AirflowFailException(str(error)) from None
                raise

        @task(task_id="publish", retry_delay=timedelta(minutes=2))
        def publish_source(path):
            from orchestration.airflow.jobs import publish_plan

            return publish_plan(path)

        @task(task_id="complete")
        def complete(path):
            from orchestration.airflow.jobs import finish_plan

            return finish_plan(path)

        planned = make_plan()
        collected = collect_source(planned)
        published = publish_source(collected)
        checked = PythonSensor(
            task_id="wait_for_database",
            python_callable=database_applied,
            op_kwargs={"path": published},
            mode="reschedule",
            poke_interval=30,
            timeout=7200,
            retries=0,
            execution_timeout=timedelta(minutes=2),
        )
        completed = complete(published)
        checked >> completed

        @task(task_id="plan_resume")
        def plan_resume(path, result):
            from orchestration.airflow.jobs import plan, read_plan
            value = read_plan(path)
            if value["mode"] != "snapshot":
                return None
            return plan(value["source"], "incremental", dag_id + ":" + get_current_context()["run_id"] + ":resume")

        @task(task_id="collect_resume", pool="food_api" if source.startswith("food-") else "safety_api")
        def collect_resume(path):
            from orchestration.airflow.jobs import collect_plan
            return collect_plan(path) if path else None

        @task(task_id="publish_resume", retry_delay=timedelta(minutes=2))
        def publish_resume(path):
            from orchestration.airflow.jobs import publish_plan
            return publish_plan(path) if path else None

        @task(task_id="complete_resume")
        def complete_resume(path):
            from orchestration.airflow.jobs import finish_plan
            return finish_plan(path) if path else None

        resumed = publish_resume(collect_resume(plan_resume(published, completed)))
        resume_checked = PythonSensor(
            task_id="wait_for_resume_database",
            python_callable=database_applied,
            op_kwargs={"path": resumed},
            mode="reschedule", poke_interval=30, timeout=7200, retries=0,
            execution_timeout=timedelta(minutes=2),
        )
        resume_checked >> complete_resume(resumed)

    return definition()


food_products = pipeline("reguard_food_products", "food-products", "30 19 * * *")
food_supplements = pipeline(
    "reguard_food_supplements", "food-supplements", "0 20 * * *"
)
food_recalls = pipeline("reguard_food_recalls", "food-recalls", "5 * * * *")
kc_products = pipeline("reguard_kc_products", "kc-products", "30 1 * * *")
safety_recalls = pipeline("reguard_safety_recalls", "safety-recalls", "15 * * * *")
food_reconcile = pipeline(
    "reguard_food_recall_reconcile", "food-recalls", "30 20 * * *", mode="reconcile"
)
food_backfill = pipeline("reguard_food_backfill", "food-recalls", None, manual=True)
safety_backfill = pipeline(
    "reguard_safety_backfill", "safety-recalls", None, manual=True
)


@dag(
    dag_id="reguard_daily_quality",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULTS, "retries": 0},
    tags=["reguard", "quality"],
)
def quality():
    @task
    def prepare():
        from orchestration.airflow.jobs import prepare_quality

        return prepare_quality("quality:" + get_current_context()["run_id"])

    def ready(path):
        from orchestration.airflow.jobs import collection_ready

        try:
            return collection_ready(path)
        except RuntimeError as error:
            raise AirflowFailException(str(error)) from None

    planned = prepare()
    waited = PythonSensor(
        task_id="wait_for_collection",
        python_callable=ready,
        op_kwargs={"path": planned},
        mode="reschedule",
        poke_interval=60,
        timeout=15000,
        retries=0,
        execution_timeout=timedelta(minutes=2),
    )

    @task
    def inspect():
        from orchestration.airflow.jobs import quality_report

        return quality_report()

    waited >> inspect()


quality_dag = quality()


@dag(
    dag_id="reguard_kc_full_reconcile",
    schedule="30 3 * * 0",
    start_date=pendulum.datetime(2026, 9, 28, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULTS, "execution_timeout": timedelta(hours=4)},
    tags=["reguard", "reconciliation"],
)
def kc_full_reconcile():
    @task(pool="safety_api")
    def snapshot():
        import os
        from uuid import NAMESPACE_URL, uuid5
        from orchestration.airflow.jobs import root
        from pipelines.bootstrap.kc import download

        directory = (
            root()
            / "kc-snapshots"
            / str(uuid5(NAMESPACE_URL, get_current_context()["run_id"]))
        )
        download(directory, os.environ["SAFETY_KOREA_API_KEY"])
        return str(directory)

    @task
    def apply_snapshot(directory):
        import os
        from pathlib import Path
        from pipelines.bootstrap.kc import load_products, load_recalls

        db = dict(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            dbname="reguard_safety",
            user="reguard_safety",
            password=os.environ["SAFETY_DB_PASSWORD"],
        )
        products = load_products(Path(directory), db)
        recalls = load_recalls(Path(directory), db)
        if products["status"] != "complete" or recalls["status"] != "complete":
            raise AirflowFailException("KC_RECONCILIATION_INCOMPLETE")
        return {
            "products": products["catalog_count"],
            "recalls": recalls["database_count"],
            "rejected_products": products["rejected"],
            "rejected_recalls": recalls["rejected"],
        }

    apply_snapshot(snapshot())


kc_full_reconcile_dag = kc_full_reconcile()


@dag(
    dag_id="reguard_recall_images",
    is_paused_upon_creation=False,
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 10, 14, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULTS, "retry_delay": timedelta(minutes=5)},
    tags=["reguard", "images"],
    description="DB에서 신규·변경 리콜과 재시도 대상을 찾아 공식 이미지 URL만 저장. 파일 저장 없음.",
)
def recall_images():
    @task(pool="safety_api")
    def enrich_image_urls():
        from orchestration.airflow.jobs import database
        from pipelines.images.worker import run

        with database() as connection:
            return run(connection, limit=100)

    enrich_image_urls()


recall_images_dag = recall_images()
