"""Populate image URL history and process due work; never save images locally."""
import argparse
import json
import os
from pathlib import Path
import sys

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.images.worker import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--sync-only', action='store_true', help='Import known URLs and queue missing ones without HTTP')
    args = parser.parse_args()
    config = {**dotenv_values(ROOT / '.env'), **os.environ}
    with psycopg.connect(host=config.get('DB_HOST', '127.0.0.1'),
                        port=config.get('DB_PORT', '15432'), dbname='reguard_safety',
                        user='reguard_safety', password=config['SAFETY_DB_PASSWORD']) as connection:
        print(json.dumps(run(connection, limit=args.limit, sync_only=args.sync_only)))


if __name__ == '__main__':
    main()
