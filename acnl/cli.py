"""
ACNL CLI - Command-line interface for the energy mesh.
"""
from __future__ import annotations

import argparse
import json
import time
import sys
from typing import Optional

from acnl.control.lfi import LocalFieldIntegrator, LFIConfig
from acnl.control.rc import RegionalCoordinator, RCConfig
from acnl.control.gh import GlobalHarmonizer, GHConfig
from acnl.integration.sensors import generate_simulated_assertions


def cmd_demo(args: argparse.Namespace) -> int:
    """Run a demo of the energy mesh."""
    print("ACNL - Autonomous Compute/Energy Nervous Layer Demo")
    print("=" * 50)

    # Create hierarchy
    region_id = args.region or "demo/region-1"

    print(f"\nInitializing LFI for region: {region_id}")
    lfi = LocalFieldIntegrator(LFIConfig(region_id=region_id))

    print("Generating simulated sensor data...")
    assertions = generate_simulated_assertions(
        region_id,
        num_compute_nodes=args.nodes,
        num_plants=args.plants,
        readings_per_entity=5,
    )
    print(f"  Generated {len(assertions)} assertions")

    lfi.ingest_assertions(assertions)
    lfi.tick()

    # Show results
    summary = lfi.get_summary()
    print(f"\nLFI Summary:")
    print(f"  Region: {summary['region_id']}")
    print(f"  Points: {summary['num_points']}")
    print(f"  Available Power: {summary['total_available_mw']:.1f} MW")
    print(f"  Consumption: {summary['total_consumption_mw']:.1f} MW")
    print(f"  Generation: {summary['total_generation_mw']:.1f} MW")
    print(f"  Carbon Intensity: {summary['avg_carbon_intensity']:.1f} gCO2/kWh")

    print(f"\nTau Limits:")
    for node_id, tau in summary['tau_limits'].items():
        print(f"  {node_id}: τ={tau:.3f}")

    # RC and GH
    print(f"\nInitializing Regional Coordinator...")
    rc = RegionalCoordinator(RCConfig(region_id=region_id))
    rc.receive_lfi_summary(summary)
    rc.tick()

    print(f"Initializing Global Harmonizer...")
    gh = GlobalHarmonizer()
    gh.receive_rc_summary(rc.get_summary())
    gh.tick()

    global_summary = gh.get_global_summary()
    print(f"\nGlobal Summary:")
    print(f"  Regions: {global_summary['num_regions']}")
    print(f"  Total Compute Nodes: {global_summary['total_compute_nodes']}")
    print(f"  Global Carbon: {global_summary['global_carbon_intensity']:.1f} gCO2/kWh")

    print("\nDemo complete!")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current mesh status."""
    print("ACNL Status")
    print("-" * 40)
    print("(Run 'acnl demo' to generate data)")
    return 0


def cmd_tau(args: argparse.Namespace) -> int:
    """Get tau limit for a node."""
    region_id = args.region or "default"
    node_id = args.node

    lfi = LocalFieldIntegrator(LFIConfig(region_id=region_id))

    # Generate some data
    assertions = generate_simulated_assertions(region_id, 3, 2, 3)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    tau_limits = lfi.get_tau_limits()

    if node_id:
        # Show specific node
        from acnl.energy.types import make_entity_id
        entity_id = make_entity_id("compute-node", node_id)
        tau = tau_limits.get(entity_id, 0.0)
        print(f"Node: {entity_id}")
        print(f"Tau Limit: {tau:.3f}")
    else:
        # Show all
        print("Tau Limits:")
        for nid, tau in tau_limits.items():
            print(f"  {nid}: {tau:.3f}")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="acnl",
        description="ACNL - Autonomous Compute/Energy Nervous Layer",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="acnl 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run demo")
    demo_parser.add_argument(
        "--region",
        default="demo/region-1",
        help="Region ID",
    )
    demo_parser.add_argument(
        "--nodes",
        type=int,
        default=3,
        help="Number of compute nodes",
    )
    demo_parser.add_argument(
        "--plants",
        type=int,
        default=2,
        help="Number of power plants",
    )
    demo_parser.set_defaults(func=cmd_demo)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.set_defaults(func=cmd_status)

    # Tau command
    tau_parser = subparsers.add_parser("tau", help="Get tau limits")
    tau_parser.add_argument(
        "--region",
        default="default",
        help="Region ID",
    )
    tau_parser.add_argument(
        "--node",
        help="Specific node ID (without prefix)",
    )
    tau_parser.set_defaults(func=cmd_tau)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
