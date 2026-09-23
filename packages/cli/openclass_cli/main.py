"""Thin HTTP client plus local server lifecycle; no classification policy here."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from openclass_sdk import OpenClass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="openclass", description="The open-world classification engine"
    )
    parser.add_argument(
        "--server", default=os.getenv("OPENCLASS_SERVER_URL", "http://localhost:7331")
    )
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Start the local API (migrate the database first)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7331)
    init = commands.add_parser("init", help="Create a classifier from a JSON configuration")
    init.add_argument("file", type=Path)
    classify = commands.add_parser("classify", help="Classify and persist an observation")
    classify.add_argument("observation")
    classify.add_argument("--classifier", default="support-intent")
    for name in ("ontology", "unknowns"):
        command = commands.add_parser(name)
        command.add_argument("--classifier", default="support-intent")
    commands.add_parser("classifiers")
    commands.add_parser("doctor", help="Check API, database and migration readiness")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "openclass_server.main:create_app", factory=True, host=args.host, port=args.port
        )
        return
    try:
        with OpenClass(args.server) as client:
            output: Any
            match args.command:
                case "init":
                    config = json.loads(args.file.read_text())
                    output = client.create_classifier(**config)
                case "classify":
                    output = client.classify(
                        classifier=args.classifier, observation=args.observation
                    )
                case "ontology":
                    output = client.ontology(args.classifier)
                case "unknowns":
                    output = client.unknowns(args.classifier)
                case "classifiers":
                    output = client.classifiers()
                case "doctor":
                    output = client.health()
                case _:
                    parser.error("Unknown command")
            print(json.dumps(output, indent=2))
    except httpx.HTTPStatusError as exc:
        print(
            f"OpenClass: server returned HTTP {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.RequestError:
        print(
            "OpenClass: could not reach server; run openclass serve or check --server",
            file=sys.stderr,
        )
        sys.exit(1)
    except (OSError, ValueError, TypeError) as exc:
        print(f"OpenClass: invalid configuration: {exc}", file=sys.stderr)
        sys.exit(1)
