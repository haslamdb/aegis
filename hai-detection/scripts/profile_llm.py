#!/usr/bin/env python3
"""LLM profiling utilities for HAI detection.

This script provides tools to analyze LLM inference performance:
1. Run extraction on test cases and collect timing data
2. Analyze stored profiles from production runs
3. Generate performance reports

Usage:
    # Show profile summary from recent runs
    python scripts/profile_llm.py summary

    # Run profiling on demo cases
    python scripts/profile_llm.py demo --scenario clabsi

    # Clear profile history
    python scripts/profile_llm.py clear

    # Export profiles to JSON
    python scripts/profile_llm.py export --output profiles.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hai_src.llm.ollama import (
    OllamaClient,
    get_profile_history,
    get_profile_summary,
    clear_profile_history,
)
from hai_src.llm.factory import get_llm_client
from hai_src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_summary(args):
    """Show summary of collected profiles."""
    summary = get_profile_summary()

    if summary.get("count", 0) == 0:
        print("No profiles collected yet.")
        print("\nRun some extractions first, or use 'profile_llm.py demo' to generate test data.")
        return

    print("\n=== LLM Profile Summary ===\n")
    print(f"Profiles collected: {summary['count']}")
    print(f"Cold starts: {summary['cold_starts']}")
    print()
    print("Timing (milliseconds):")
    print(f"  Average total:      {summary['avg_total_ms']:>8.1f} ms")
    print(f"  Average prefill:    {summary['avg_prefill_ms']:>8.1f} ms")
    print(f"  Average generation: {summary['avg_generation_ms']:>8.1f} ms")
    print(f"  P50 total:          {summary['p50_total_ms']:>8.1f} ms")
    print(f"  P95 total:          {summary['p95_total_ms']:>8.1f} ms")
    print()
    print("Tokens:")
    print(f"  Average input:      {summary['avg_input_tokens']:>8.0f} tokens")
    print(f"  Average output:     {summary['avg_output_tokens']:>8.0f} tokens")
    print(f"  Generation speed:   {summary['avg_tokens_per_second']:>8.1f} tok/s")
    print()

    # Show breakdown analysis
    avg_total = summary['avg_total_ms']
    if avg_total > 0:
        prefill_pct = (summary['avg_prefill_ms'] / avg_total) * 100
        gen_pct = (summary['avg_generation_ms'] / avg_total) * 100
        other_pct = 100 - prefill_pct - gen_pct

        print("Time breakdown:")
        print(f"  Prefill:    {prefill_pct:>5.1f}%")
        print(f"  Generation: {gen_pct:>5.1f}%")
        print(f"  Other:      {other_pct:>5.1f}% (loading, overhead)")


def cmd_history(args):
    """Show detailed profile history."""
    history = get_profile_history()

    if not history:
        print("No profiles in history.")
        return

    print(f"\n=== Profile History ({len(history)} entries) ===\n")

    for i, p in enumerate(history[-20:], 1):  # Show last 20
        ts = datetime.fromtimestamp(p['timestamp']).strftime('%H:%M:%S')
        ctx = p.get('context', 'unnamed')
        print(f"{i:2}. [{ts}] {ctx}")
        print(f"    in={p['input_tokens']}tok out={p['output_tokens']}tok "
              f"total={p['total_ms']:.0f}ms gen={p['generation_ms']:.0f}ms "
              f"({p['tokens_per_second']:.1f}tok/s)")
        if p.get('model_was_cold'):
            print(f"    [COLD START: load={p['load_ms']:.0f}ms]")
        print()


def cmd_clear(args):
    """Clear profile history."""
    clear_profile_history()
    print("Profile history cleared.")


def cmd_export(args):
    """Export profiles to JSON."""
    history = get_profile_history()
    summary = get_profile_summary()

    output = {
        "exported_at": datetime.now().isoformat(),
        "summary": summary,
        "profiles": history,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2))
    print(f"Exported {len(history)} profiles to {output_path}")


def cmd_demo(args):
    """Run demo extraction to collect profiles."""
    print(f"\n=== Running Demo Extraction ({args.scenario}) ===\n")

    # Check if Ollama is available
    client = get_llm_client()
    if not client.is_available():
        print("ERROR: Ollama is not available. Make sure it's running.")
        print(f"Expected at: {Config.OLLAMA_BASE_URL}")
        return 1

    print(f"Model: {client.model_name}")
    print(f"Context window: {client.num_ctx}")
    print()

    # Create a simple test prompt based on scenario
    test_prompts = {
        "clabsi": {
            "context": "clabsi_extraction_demo",
            "prompt": """Extract clinical information for CLABSI evaluation.

Patient: TEST001
Culture Date: 2024-01-15
Organism: Staphylococcus epidermidis
Device Type: PICC
Device Days: 14

Notes:
--- PROGRESS NOTE (2024-01-15) ---
Patient is a 45-year-old with ALL s/p allo-SCT day +42, now with fever
and positive blood cultures. PICC line has been in place for 14 days.
Exit site appears clean without erythema or drainage.

Assessment/Plan:
1. Bacteremia - likely line-related given timing and organism
   - Obtaining repeat cultures
   - Started vancomycin empirically
   - Will discuss line removal with primary team
2. ANC recovering, currently 800

Extract: alternate infection sources, symptoms, MBI factors, line assessment, contamination signals.
Respond with JSON.""",
        },
        "simple": {
            "context": "simple_demo",
            "prompt": """Summarize in JSON format:
{"summary": "brief summary here", "key_points": ["point 1", "point 2"]}

Text: The patient was admitted with pneumonia and started on antibiotics.
Cultures are pending. Fever has resolved.""",
        },
    }

    test = test_prompts.get(args.scenario, test_prompts["simple"])

    print(f"Running {args.iterations} iteration(s)...\n")

    for i in range(args.iterations):
        print(f"Iteration {i+1}/{args.iterations}...")
        try:
            response = client.generate(
                prompt=test["prompt"],
                profile_context=test["context"],
            )
            print(f"  Completed: {response.profile.summary()}")
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "="*50)
    cmd_summary(args)
    return 0


def cmd_benchmark(args):
    """Run benchmark with varying context sizes."""
    print("\n=== Context Size Benchmark ===\n")

    client = get_llm_client()
    if not client.is_available():
        print("ERROR: Ollama is not available.")
        return 1

    # Generate prompts of varying sizes
    base_text = "The patient is stable. Vitals are normal. No acute issues. " * 50  # ~500 chars

    context_sizes = [1000, 2000, 4000, 8000, 16000]

    print(f"Model: {client.model_name}")
    print(f"Testing context sizes: {context_sizes}")
    print()

    results = []

    for size in context_sizes:
        # Build prompt of approximately target size
        multiplier = max(1, size // 500)
        text = (base_text * multiplier)[:size]

        prompt = f"""Summarize in JSON format:
{{"summary": "brief summary", "length": "short/medium/long"}}

Clinical Notes:
{text}"""

        print(f"Testing {size} chars...")

        try:
            response = client.generate(
                prompt=prompt,
                profile_context=f"benchmark_{size}",
            )
            profile = response.profile
            results.append({
                "context_chars": size,
                "input_tokens": profile.input_tokens,
                "output_tokens": profile.output_tokens,
                "total_ms": profile.total_ms,
                "prefill_ms": profile.prefill_ms,
                "generation_ms": profile.generation_ms,
            })
            print(f"  {profile.summary()}")
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"context_chars": size, "error": str(e)})

    print("\n=== Results ===\n")
    print(f"{'Context':>10} {'Tokens':>10} {'Total':>10} {'Prefill':>10} {'Generate':>10}")
    print("-" * 55)

    for r in results:
        if "error" in r:
            print(f"{r['context_chars']:>10} ERROR: {r['error']}")
        else:
            print(f"{r['context_chars']:>10} {r['input_tokens']:>10} "
                  f"{r['total_ms']:>10.0f}ms {r['prefill_ms']:>10.0f}ms "
                  f"{r['generation_ms']:>10.0f}ms")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="LLM profiling utilities for HAI detection"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # summary command
    sub = subparsers.add_parser("summary", help="Show profile summary")
    sub.set_defaults(func=cmd_summary)

    # history command
    sub = subparsers.add_parser("history", help="Show detailed profile history")
    sub.set_defaults(func=cmd_history)

    # clear command
    sub = subparsers.add_parser("clear", help="Clear profile history")
    sub.set_defaults(func=cmd_clear)

    # export command
    sub = subparsers.add_parser("export", help="Export profiles to JSON")
    sub.add_argument("--output", "-o", default="profiles.json",
                     help="Output file path")
    sub.set_defaults(func=cmd_export)

    # demo command
    sub = subparsers.add_parser("demo", help="Run demo extraction")
    sub.add_argument("--scenario", "-s", default="simple",
                     choices=["simple", "clabsi"],
                     help="Demo scenario to run")
    sub.add_argument("--iterations", "-n", type=int, default=3,
                     help="Number of iterations")
    sub.set_defaults(func=cmd_demo)

    # benchmark command
    sub = subparsers.add_parser("benchmark", help="Run context size benchmark")
    sub.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
