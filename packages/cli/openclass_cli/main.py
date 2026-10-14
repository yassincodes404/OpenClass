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
    for name in ("ontology", "unknowns", "runs", "reviews"):
        command = commands.add_parser(name)
        command.add_argument("--classifier", default="support-intent")
    review = commands.add_parser(
        "review", help="Request an advisory supervisor review of a classification run"
    )
    review.add_argument("run_id")
    review.add_argument("--classifier", default="support-intent")
    commands.add_parser("classifiers")
    commands.add_parser("projects", help="List all projects")
    project_create = commands.add_parser("project-create", help="Create a project")
    project_create.add_argument("name")
    project_create.add_argument("--description", default="")
    cluster_cmd = commands.add_parser("cluster", help="Cluster UNKNOWN runs in a project")
    cluster_cmd.add_argument("project")
    cluster_cmd.add_argument("--threshold", type=float, default=None)
    clusters_cmd = commands.add_parser("clusters", help="List UNKNOWN clusters in a project")
    clusters_cmd.add_argument("project")
    discover_cmd = commands.add_parser(
        "discover", help="Propose an inactive candidate from a cluster"
    )
    discover_cmd.add_argument("project")
    discover_cmd.add_argument("cluster_id")
    candidates_cmd = commands.add_parser(
        "discovery-candidates", help="List discovery candidates for a project"
    )
    candidates_cmd.add_argument("project")
    eval_run_cmd = commands.add_parser(
        "eval-run", help="Run a verified replay evaluation for a candidate"
    )
    eval_run_cmd.add_argument("project")
    eval_run_cmd.add_argument("--dataset-id", required=True)
    eval_run_cmd.add_argument("--candidate-id", required=True)
    eval_run_cmd.add_argument("--service-id", default=None)
    promote_cmd = commands.add_parser(
        "promote", help="Promote an approved and evaluated discovery candidate"
    )
    promote_cmd.add_argument("project")
    promote_cmd.add_argument("candidate_id")
    promote_cmd.add_argument("--evaluation-id", required=True)
    promote_cmd.add_argument("--reviewer", required=True)
    promote_cmd.add_argument("--rationale", required=True)
    ops_cmd = commands.add_parser("ops-summary", help="Fetch operations summary for a project")
    ops_cmd.add_argument("project")
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
                case "runs":
                    output = client.runs(args.classifier)
                case "reviews":
                    output = client.reviews(args.classifier)
                case "review":
                    output = client.review_run(classifier=args.classifier, run_id=args.run_id)
                case "classifiers":
                    output = client.classifiers()
                case "projects":
                    output = client.projects()
                case "project-create":
                    output = client.create_project(name=args.name, description=args.description)
                case "cluster":
                    output = client.cluster_unknowns(args.project, threshold=args.threshold)
                case "clusters":
                    output = client.clusters(args.project)
                case "discover":
                    output = client.discover_cluster(args.project, args.cluster_id)
                case "discovery-candidates":
                    output = client.discovery_candidates(args.project)
                case "eval-run":
                    output = client.run_evaluation(
                        args.project,
                        dataset_id=args.dataset_id,
                        candidate_id=args.candidate_id,
                        service_id=args.service_id,
                    )
                case "promote":
                    output = client.promote_discovery_candidate(
                        args.project,
                        args.candidate_id,
                        evaluation_id=args.evaluation_id,
                        reviewer=args.reviewer,
                        rationale=args.rationale,
                    )
                case "ops-summary":
                    output = client.operations_summary(args.project)
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
