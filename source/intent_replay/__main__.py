import argparse
from pathlib import Path

import uvicorn


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Intent Replay report.")
    parser.add_argument("--port", type=int, default=8000)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Open recorded Meta evidence, read-only and without a key (default).")
    mode.add_argument("--developer", action="store_true", help="Keep the original optional live/synthetic developer workflows.")
    mode.add_argument("--benchmark", action="store_true", help="Open the new bounded proposal-only benchmark workflow.")
    parser.add_argument("--benchmark-dir", type=Path, help="Optional benchmark report directory; the durable budget authority stays fixed.")
    parser.add_argument("--demo-dir", type=Path, help="Optional isolated saved-report directory; conflicts are never overwritten.")
    arguments = parser.parse_args(argv)
    from intent_replay.app import app
    if (arguments.developer or arguments.benchmark) and arguments.demo_dir:
        parser.error("--demo-dir is only available in recorded-demo mode.")
    if arguments.benchmark_dir and not arguments.benchmark:
        parser.error("--benchmark-dir requires --benchmark.")
    if arguments.benchmark:
        from intent_replay.benchmark_api import configure_benchmark
        configure_benchmark(app, arguments.benchmark_dir)
        print(f"Proposal-only execution benchmark: http://127.0.0.1:{arguments.port} — live requests are ledger/credit gated; prepared replay needs no key.", flush=True)
    elif not arguments.developer:
        from intent_replay.demo import configure_demo
        try:
            configure_demo(app, arguments.demo_dir)
        except (OSError, ValueError, KeyError):
            parser.error("Recorded demo could not be installed safely. Check demo/ hashes and choose a non-conflicting --demo-dir.")
        print(f"Recorded Meta comparison: http://127.0.0.1:{arguments.port} — no key or API requests; live actions disabled.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=arguments.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
