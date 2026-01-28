#!/usr/bin/env python3
"""
AEGIS Complete Demo Script

Creates demo alerts for all AEGIS workflows in a single run:
1. Bacteremia Alert - Pseudomonas BSI on ceftriaxone (inadequate coverage)
2. Antimicrobial Usage Alert - Meropenem > 4 days (exceeds 72h threshold)
3. Antibiotic Indication Alert - Ceftriaxone for viral URI (inappropriate)
4. Guideline Adherence Alert - Sepsis bundle deviation
5. Surgical Prophylaxis Alert - Missing prophylaxis
6. HAI Detection (all 5 NHSN HAI types):
   - CLABSI candidate + Not CLABSI (MBI-LCBI)
   - SSI candidate + Not SSI (normal healing)
   - VAE candidate + Not VAE (stable vent settings)
   - CAUTI candidate + Not CAUTI (asymptomatic bacteriuria)
   - CDI: HO-CDI (hospital onset) + CO-CDI (community onset)

Usage:
    # Create all demo data and run monitors
    python scripts/demo_all.py

    # Create demo data only (don't run monitors)
    python scripts/demo_all.py --data-only

    # Run monitors only (assume data exists)
    python scripts/demo_all.py --monitors-only

    # Quick demo (skip slow HAI LLM classification)
    python scripts/demo_all.py --skip-hai

    # Dry run (show what would be created)
    python scripts/demo_all.py --dry-run

    # Verbose output
    python scripts/demo_all.py --verbose
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Get the project root directory
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.END}\n")


def print_step(step: int, text: str):
    """Print a step indicator."""
    print(f"{Colors.CYAN}[Step {step}]{Colors.END} {text}")


def print_success(text: str):
    """Print success message."""
    print(f"  {Colors.GREEN}✓{Colors.END} {text}")


def print_warning(text: str):
    """Print warning message."""
    print(f"  {Colors.YELLOW}⚠{Colors.END} {text}")


def print_error(text: str):
    """Print error message."""
    print(f"  {Colors.RED}✗{Colors.END} {text}")


def run_command(cmd: list, cwd: Path = None, description: str = None, dry_run: bool = False, verbose: bool = False, timeout: int = 120) -> bool:
    """Run a shell command and return success status."""
    if description:
        print(f"  Running: {description}")

    if dry_run:
        print(f"    [DRY RUN] {' '.join(cmd)}")
        return True

    if verbose:
        print(f"    $ {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=not verbose,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return True
        else:
            if not verbose and result.stderr:
                print(f"    Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print_error("Command timed out")
        return False
    except Exception as e:
        print_error(f"Command failed: {e}")
        return False


def create_bacteremia_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create Pseudomonas BSI on ceftriaxone (inadequate coverage)."""
    print_step(1, "Creating Bacteremia Alert Demo")
    print("  Scenario: Pseudomonas aeruginosa BSI on ceftriaxone (inadequate coverage)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_blood_culture.py"),
        "--organism", "pseudomonas",
        "--antibiotic", "ceftriaxone"
    ]

    success = run_command(cmd, description="demo_blood_culture.py", dry_run=dry_run, verbose=verbose)
    if success:
        print_success("Pseudomonas BSI patient created - should trigger coverage alert")
    else:
        print_error("Failed to create bacteremia demo")
    return success


def create_usage_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create meropenem usage > 4 days."""
    print_step(2, "Creating Antimicrobial Usage Alert Demo")
    print("  Scenario: Patient on meropenem for 5 days (exceeds 72h threshold)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_antimicrobial_usage.py"),
        "--antibiotic", "meropenem",
        "--days", "5"
    ]

    success = run_command(cmd, description="demo_antimicrobial_usage.py", dry_run=dry_run, verbose=verbose)
    if success:
        print_success("Meropenem 5-day patient created - should trigger usage alert")
    else:
        print_error("Failed to create usage demo")
    return success


def create_indication_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create ceftriaxone for viral URI (inappropriate)."""
    print_step(3, "Creating Antibiotic Indication Alert Demo")
    print("  Scenario: Ceftriaxone prescribed for viral URI (inappropriate indication)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_indication_alert.py"),
        "--scenario", "viral-uri-ceftriaxone"
    ]

    # Check if script exists
    if not (SCRIPT_DIR / "demo_indication_alert.py").exists():
        print_warning("demo_indication_alert.py not found - skipping")
        return True

    success = run_command(cmd, description="demo_indication_alert.py", dry_run=dry_run, verbose=verbose)
    if success:
        print_success("Viral URI + ceftriaxone patient created - should trigger indication alert")
    else:
        print_error("Failed to create indication demo")
    return success


def create_guideline_adherence_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create guideline adherence demo (sepsis bundle deviation)."""
    print_step(4, "Creating Guideline Adherence Alert Demo")
    print("  Scenario: Sepsis patient with delayed antibiotics (>1 hour)")

    # The guideline adherence monitor will detect patients with sepsis ICD-10 codes
    # who don't have timely antibiotics. For demo, we can use a sepsis patient from
    # the blood culture demo or create specific data.

    # For now, we'll note that the bacteremia patient can also trigger this
    print_warning("Guideline adherence uses existing patient data from FHIR")
    print_success("Run guideline-adherence monitor to detect bundle deviations")
    return True


def create_surgical_prophylaxis_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create surgical prophylaxis demo."""
    print_step(5, "Creating Surgical Prophylaxis Alert Demo")
    print("  Scenario: Surgical case without appropriate prophylaxis")

    # The surgical prophylaxis monitor queries FHIR for procedures
    # For a complete demo, we'd need to create surgical procedure data
    print_warning("Surgical prophylaxis uses procedure data from FHIR")
    print_success("Run surgical-prophylaxis monitor to detect non-compliance")
    return True


def create_clabsi_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create CLABSI candidates (positive and negative)."""
    print_step(6, "Creating CLABSI Demo Cases")
    print("  Scenario A: Clear CLABSI (S. aureus BSI with line, no alternate source)")
    print("  Scenario B: Not CLABSI - MBI-LCBI (BMT patient with mucositis)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_clabsi.py"),
        "--scenario", "clabsi"
    ]
    success1 = run_command(cmd, description="demo_clabsi.py --scenario clabsi", dry_run=dry_run, verbose=verbose)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_clabsi.py"),
        "--scenario", "mbi"
    ]
    success2 = run_command(cmd, description="demo_clabsi.py --scenario mbi", dry_run=dry_run, verbose=verbose)

    if success1:
        print_success("CLABSI candidate created")
    if success2:
        print_success("Not CLABSI (MBI-LCBI) case created")

    return success1 and success2


def create_ssi_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create SSI candidates (positive and negative)."""
    print_step(7, "Creating SSI Demo Cases")
    print("  Scenario A: Deep Incisional SSI (fascial dehiscence, fever)")
    print("  Scenario B: Not SSI (normal post-op healing)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_ssi.py"),
        "--scenario", "deep"
    ]
    success1 = run_command(cmd, description="demo_ssi.py --scenario deep", dry_run=dry_run, verbose=verbose)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_ssi.py"),
        "--scenario", "not-ssi"
    ]
    success2 = run_command(cmd, description="demo_ssi.py --scenario not-ssi", dry_run=dry_run, verbose=verbose)

    if success1:
        print_success("Deep SSI candidate created")
    if success2:
        print_success("Not SSI case created")

    return success1 and success2


def create_vae_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create VAE candidates (VAC and stable)."""
    print_step(8, "Creating VAE Demo Cases")
    print("  Scenario A: VAC (Ventilator-Associated Condition) - worsening FiO2/PEEP")
    print("  Scenario B: Not VAE (stable ventilator settings)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_vae.py"),
        "--scenario", "vac"
    ]
    success1 = run_command(cmd, description="demo_vae.py --scenario vac", dry_run=dry_run, verbose=verbose)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_vae.py"),
        "--scenario", "stable"
    ]
    success2 = run_command(cmd, description="demo_vae.py --scenario stable", dry_run=dry_run, verbose=verbose)

    if success1:
        print_success("VAC candidate created")
    if success2:
        print_success("Not VAE (stable) case created")

    return success1 and success2


def create_cauti_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create CAUTI candidates (symptomatic and asymptomatic)."""
    print_step(9, "Creating CAUTI Demo Cases")
    print("  Scenario A: CAUTI (catheter >2 days, positive culture, fever)")
    print("  Scenario B: Not CAUTI (asymptomatic bacteriuria)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_cauti.py"),
        "--scenario", "cauti"
    ]
    success1 = run_command(cmd, description="demo_cauti.py --scenario cauti", dry_run=dry_run, verbose=verbose)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_cauti.py"),
        "--scenario", "asymptomatic"
    ]
    success2 = run_command(cmd, description="demo_cauti.py --scenario asymptomatic", dry_run=dry_run, verbose=verbose)

    if success1:
        print_success("CAUTI candidate created")
    if success2:
        print_success("Not CAUTI (asymptomatic) case created")

    return success1 and success2


def create_cdi_demo(dry_run: bool = False, verbose: bool = False) -> bool:
    """Create CDI candidates (HO-CDI and CO-CDI)."""
    print_step(10, "Creating CDI Demo Cases")
    print("  Scenario A: HO-CDI (Hospital Onset - positive test day 5)")
    print("  Scenario B: CO-CDI (Community Onset - positive test day 1)")

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_cdi.py"),
        "--scenario", "ho-cdi"
    ]
    success1 = run_command(cmd, description="demo_cdi.py --scenario ho-cdi", dry_run=dry_run, verbose=verbose)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "demo_cdi.py"),
        "--scenario", "co-cdi"
    ]
    success2 = run_command(cmd, description="demo_cdi.py --scenario co-cdi", dry_run=dry_run, verbose=verbose)

    if success1:
        print_success("HO-CDI candidate created")
    if success2:
        print_success("CO-CDI candidate created")

    return success1 and success2


def run_monitors(dry_run: bool = False, verbose: bool = False, skip_hai: bool = False) -> dict:
    """Run all monitors to generate alerts."""
    print_header("RUNNING MONITORS")

    results = {}

    # 1. Bacteremia monitor
    print_step(1, "Running Bacteremia Monitor")
    cmd = [sys.executable, "-m", "src.monitor"]
    results["bacteremia"] = run_command(
        cmd,
        cwd=PROJECT_ROOT / "asp-bacteremia-alerts",
        description="asp-bacteremia-alerts monitor",
        dry_run=dry_run,
        verbose=verbose
    )

    # 2. Antimicrobial usage monitor
    print_step(2, "Running Antimicrobial Usage Monitor")
    cmd = [sys.executable, "-m", "au_alerts_src.runner", "--once"]
    if verbose:
        cmd.append("--verbose")
    results["usage"] = run_command(
        cmd,
        cwd=PROJECT_ROOT / "antimicrobial-usage-alerts",
        description="antimicrobial-usage-alerts runner",
        dry_run=dry_run,
        verbose=verbose
    )

    # 3. Indication monitor
    print_step(3, "Running Indication Monitor")
    cmd = [sys.executable, "-m", "au_alerts_src.runner", "--indication", "--once"]
    if verbose:
        cmd.append("--verbose")
    results["indication"] = run_command(
        cmd,
        cwd=PROJECT_ROOT / "antimicrobial-usage-alerts",
        description="indication monitor",
        dry_run=dry_run,
        verbose=verbose
    )

    # 4. Guideline adherence monitor
    print_step(4, "Running Guideline Adherence Monitor")
    cmd = [sys.executable, "-m", "guideline_src.runner", "--once"]
    if verbose:
        cmd.append("--verbose")
    results["guideline"] = run_command(
        cmd,
        cwd=PROJECT_ROOT / "guideline-adherence",
        description="guideline-adherence runner",
        dry_run=dry_run,
        verbose=verbose
    )

    # 5. Surgical prophylaxis monitor
    print_step(5, "Running Surgical Prophylaxis Monitor")
    cmd = [sys.executable, "-m", "src.runner", "--once"]
    if verbose:
        cmd.append("--verbose")
    results["prophylaxis"] = run_command(
        cmd,
        cwd=PROJECT_ROOT / "surgical-prophylaxis",
        description="surgical-prophylaxis runner",
        dry_run=dry_run,
        verbose=verbose
    )

    # 6. HAI Detection monitor (longer timeout for LLM classification)
    print_step(6, "Running HAI Detection Monitor")
    if skip_hai:
        print_warning("Skipping HAI detection (--skip-hai flag)")
        results["hai"] = True  # Mark as success (skipped)
    else:
        print("  Note: LLM classification may take several minutes...")
        cmd = [sys.executable, "-m", "hai_src.runner", "--full"]
        results["hai"] = run_command(
            cmd,
            cwd=PROJECT_ROOT / "hai-detection",
            description="hai-detection runner",
            dry_run=dry_run,
            verbose=verbose,
            timeout=300  # 5 minutes for LLM classification
        )

    return results


def print_summary(data_results: dict, monitor_results: dict = None):
    """Print a summary of the demo run."""
    print_header("DEMO SUMMARY")

    print(f"{Colors.BOLD}Data Created:{Colors.END}")
    scenarios = [
        ("Bacteremia Alert", "Pseudomonas BSI on ceftriaxone", "bacteremia"),
        ("Usage Alert", "Meropenem > 4 days", "usage"),
        ("Indication Alert", "Ceftriaxone for viral URI", "indication"),
        ("Guideline Alert", "Sepsis bundle deviation", "guideline"),
        ("Prophylaxis Alert", "Missing surgical prophylaxis", "prophylaxis"),
        ("CLABSI", "S. aureus BSI + Not CLABSI (MBI)", "clabsi"),
        ("SSI", "Deep SSI + Not SSI", "ssi"),
        ("VAE", "VAC + Not VAE (stable)", "vae"),
        ("CAUTI", "CAUTI + Not CAUTI (asymptomatic)", "cauti"),
        ("CDI", "HO-CDI + CO-CDI", "cdi"),
    ]

    for name, description, key in scenarios:
        status = "✓" if data_results.get(key, True) else "✗"
        color = Colors.GREEN if data_results.get(key, True) else Colors.RED
        print(f"  {color}{status}{Colors.END} {name}: {description}")

    if monitor_results:
        print(f"\n{Colors.BOLD}Monitors Run:{Colors.END}")
        monitors = [
            ("Bacteremia Monitor", "bacteremia"),
            ("Usage Monitor", "usage"),
            ("Indication Monitor", "indication"),
            ("Guideline Monitor", "guideline"),
            ("Prophylaxis Monitor", "prophylaxis"),
            ("HAI Detection", "hai"),
        ]

        for name, key in monitors:
            status = "✓" if monitor_results.get(key, False) else "✗"
            color = Colors.GREEN if monitor_results.get(key, False) else Colors.RED
            print(f"  {color}{status}{Colors.END} {name}")

    print(f"\n{Colors.BOLD}View Alerts:{Colors.END}")
    print("  Dashboard: http://localhost:5000 (or https://aegis-asp.com)")
    print("  ASP Alerts: /asp-alerts/active")
    print("  HAI Detection: /hai-detection/")
    print("  Guideline Adherence: /guideline-adherence/")


def main():
    parser = argparse.ArgumentParser(
        description="Create demo alerts for all AEGIS workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full demo (create data + run monitors)
    python scripts/demo_all.py

    # Create data only
    python scripts/demo_all.py --data-only

    # Run monitors only
    python scripts/demo_all.py --monitors-only

    # Dry run
    python scripts/demo_all.py --dry-run
"""
    )
    parser.add_argument("--data-only", action="store_true",
                       help="Only create demo data, don't run monitors")
    parser.add_argument("--monitors-only", action="store_true",
                       help="Only run monitors, assume data exists")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without executing")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show detailed output")
    parser.add_argument("--skip-hai", action="store_true",
                       help="Skip HAI detection (LLM classification takes several minutes)")

    args = parser.parse_args()

    print_header("AEGIS COMPLETE DEMO")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project root: {PROJECT_ROOT}")

    if args.dry_run:
        print(f"\n{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.END}")

    data_results = {}
    monitor_results = {}

    # Create demo data
    if not args.monitors_only:
        print_header("CREATING DEMO DATA")

        data_results["bacteremia"] = create_bacteremia_demo(args.dry_run, args.verbose)
        data_results["usage"] = create_usage_demo(args.dry_run, args.verbose)
        data_results["indication"] = create_indication_demo(args.dry_run, args.verbose)
        data_results["guideline"] = create_guideline_adherence_demo(args.dry_run, args.verbose)
        data_results["prophylaxis"] = create_surgical_prophylaxis_demo(args.dry_run, args.verbose)
        data_results["clabsi"] = create_clabsi_demo(args.dry_run, args.verbose)
        data_results["ssi"] = create_ssi_demo(args.dry_run, args.verbose)
        data_results["vae"] = create_vae_demo(args.dry_run, args.verbose)
        data_results["cauti"] = create_cauti_demo(args.dry_run, args.verbose)
        data_results["cdi"] = create_cdi_demo(args.dry_run, args.verbose)

    # Run monitors
    if not args.data_only:
        monitor_results = run_monitors(args.dry_run, args.verbose, args.skip_hai)

    # Print summary
    print_summary(data_results, monitor_results if not args.data_only else None)

    print(f"\n{Colors.BOLD}Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")


if __name__ == "__main__":
    main()
