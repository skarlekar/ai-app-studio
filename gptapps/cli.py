import argparse
import json
import os
from pathlib import Path

from .extensions import Registry
from .spec import analyze, import_export, load


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Import owned GPTs into standalone OpenAI applications")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("import", help="Normalize an owner-provided GPT export")
    convert.add_argument("source", type=Path)
    convert.add_argument("--out", required=True, type=Path)
    check = sub.add_parser("check", help="Analyze an application manifest")
    check.add_argument("spec", type=Path)
    check.add_argument('--release-report',type=Path,help='Require a current, executed and human-reviewed evaluation report')
    evaluation=sub.add_parser('evaluate',help='Prepare an owner-review report; --execute explicitly runs paid baseline/candidate requests')
    evaluation.add_argument('spec',type=Path)
    evaluation.add_argument('--suite',type=Path,required=True)
    evaluation.add_argument('--out',type=Path,required=True)
    evaluation.add_argument('--execute',action='store_true')
    evaluation.add_argument('--data',type=Path,default=Path('.gptapps-data/evaluation-runs'))
    evaluation.add_argument('--extension',action='append',default=[])
    server = sub.add_parser("serve", help="Run the local chat application")
    server.add_argument("--apps", required=True, type=Path)
    server.add_argument("--data", type=Path, default=Path(".gptapps-data"))
    server.add_argument("--routing-policy", type=Path, help="Validated server policy used when creating Auto apps")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1",
                        help="Bind address; use 0.0.0.0 inside a locally published container")
    server.add_argument("--extension", action="append", default=[], help="Trusted module:setup function")
    server.add_argument("--builder", action="store_true", help="Enable conversational app setup for a local apps directory")
    build = sub.add_parser("build", help="Create a self-contained single-GPT application folder")
    build.add_argument("spec", type=Path)
    build.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "import":
            apps = import_export(json.loads(args.source.read_text()))
            reports = [analyze(app) for app in apps]
            args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
            (args.out / "apps").mkdir()
            for app in apps:
                write_json(args.out / "apps" / f"{app['id']}.json", app)
            write_json(args.out / "report.json", {"application_count": len(apps), "applications": reports,
                "scope": "Configuration import; runtime-ready does not certify behavioral equivalence or production readiness."})
            print(f"Imported {len(apps)} GPTs into {args.out}. Review report.json before running.")
        elif args.command == "check":
            app=load(args.spec);report = analyze(app)
            if args.release_report:
                from .evaluation import release_gate
                report['evaluation']=release_gate(app,json.loads(args.release_report.read_text()))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if not report["runtime_ready"] or (args.release_report and not report['evaluation']['approved']):
                raise SystemExit(2)
        elif args.command=='evaluate':
            from .evaluation import prepare_report,run_suite,release_gate
            app=load(args.spec);suite=json.loads(args.suite.read_text())
            report=prepare_report(app,suite)
            if args.execute:
                from .runtime import Runtime
                registry=Registry()
                for reference in args.extension:registry.load(reference)
                runtime=Runtime(args.data,registry=registry)
                try:report=run_suite(app,suite,lambda config,prompt,files:runtime.chat(config,prompt,attachments=files))
                finally:runtime.close()
            args.out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with args.out.open('x') as file:
                args.out.chmod(0o600);json.dump(report,file,ensure_ascii=False,indent=2);file.write('\n')
            print(json.dumps({'report':str(args.out),'evaluation':release_gate(app,report)},indent=2))
        elif args.command == "serve":
            from .web import serve
            registry = Registry()
            for reference in args.extension:
                registry.load(reference)
            if args.routing_policy is not None:
                os.environ["OPENAI_ROUTING_POLICY_FILE"]=str(args.routing_policy.resolve())
                from .routing import load_policy_file
                load_policy_file()
            serve(args.apps, args.data, args.port, registry, builder=args.builder, host=args.host)
        elif args.command == "build":
            from .build import build_app
            app = load(args.spec)
            build_app(app, args.out)
            print(f"Built standalone application: {args.out}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
