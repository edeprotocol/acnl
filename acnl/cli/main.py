"""
ACNL CLI — Main Entry Point

Command line interface for ACNL mesh operations.
"""

from __future__ import annotations
import time
import json
from typing import Optional

import typer

app = typer.Typer(
    name="acnl",
    help="ACNL - Autonomous Compute/Energy Nervous Layer",
    add_completion=False,
)


@app.command()
def demo(
    region: str = typer.Option(
        "earth/demo",
        "--region", "-r",
        help="Region ID for demo",
    ),
    ticks: int = typer.Option(
        10,
        "--ticks", "-t",
        help="Number of ticks to run",
    ),
    interval_ms: int = typer.Option(
        500,
        "--interval", "-i",
        help="Tick interval in milliseconds",
    ),
) -> None:
    """Run a demo of the ACNL mesh."""
    from ..core.ids import compute_node_id, plant_id
    from ..integration.sensors import SimulatedSensor
    from ..runtime.lfi_runtime import LFIRuntime, LFIConfig

    typer.echo(f"ACNL Demo - Region: {region}")
    typer.echo("=" * 50)

    # Create LFI runtime
    config = LFIConfig(
        region_id=region,
        tick_interval_ms=interval_ms,
    )
    runtime = LFIRuntime(config)

    # Add simulated sensor
    sensor = SimulatedSensor(
        region_id=region,
        plant_ids=[plant_id("solar-1"), plant_id("wind-1")],
        compute_node_ids=[
            compute_node_id("gpu-cluster-1"),
            compute_node_id("cpu-cluster-1"),
        ],
    )
    runtime.add_sensor(sensor)

    # Run ticks
    for i in range(ticks):
        runtime.tick()
        field = runtime.lfi.get_field()

        if field:
            typer.echo(f"\nTick {i+1}/{ticks}")
            typer.echo(f"  Plants: {len(field.plants())}")
            typer.echo(f"  Compute nodes: {len(field.compute_nodes())}")
            typer.echo(f"  Total generation: {field.total_generation_mw():.2f} MW")
            typer.echo(f"  Total consumption: {field.total_consumption_mw():.2f} MW")
            typer.echo(f"  Avg carbon: {field.avg_carbon_intensity():.1f} gCO2/kWh")

            # Show tau limits
            limits = runtime.lfi.get_tau_limits()
            if limits:
                typer.echo("  Tau limits:")
                for entity_id, tau in limits.items():
                    typer.echo(f"    {entity_id}: {tau:.3f}")

        time.sleep(interval_ms / 1000.0)

    typer.echo("\nDemo complete.")
    stats = runtime.get_stats()
    typer.echo(f"Total ticks: {stats['tick_count']}")
    typer.echo(f"Total assertions: {stats['assertion_count']}")


@app.command()
def mesh_demo(
    ticks: int = typer.Option(
        5,
        "--ticks", "-t",
        help="Number of ticks to run",
    ),
) -> None:
    """Run a demo of the full mesh hierarchy."""
    from ..core.ids import compute_node_id, plant_id
    from ..integration.sensors import generate_simulated_assertions
    from ..runtime.mesh_runtime import MeshRuntime, MeshConfig

    typer.echo("ACNL Mesh Demo - Fractal Hierarchy")
    typer.echo("=" * 50)

    # Create mesh
    config = MeshConfig(
        tick_interval_ms=500,
        rc_tick_interval_ms=1000,
        gh_tick_interval_ms=2000,
    )
    mesh = MeshRuntime(config)
    mesh.setup_demo_mesh()

    typer.echo(f"Created {mesh.get_stats()['lfi_count']} LFIs")
    typer.echo(f"Created {mesh.get_stats()['rc_count']} RCs")
    typer.echo(f"GH active: {mesh.get_stats()['has_gh']}")

    # Inject some data into each LFI
    for region_id in ["earth/us/west/dc-1", "earth/us/east/dc-1", "earth/eu/west/dc-1"]:
        lfi = mesh.get_lfi(region_id)
        if lfi:
            assertions = generate_simulated_assertions(
                region_id=region_id,
                plant_count=2,
                compute_count=3,
            )
            for a in assertions:
                lfi.store.add_assertion(a)
                lfi._builder.ingest(a)

    # Run ticks
    for i in range(ticks):
        mesh.tick()

        typer.echo(f"\nTick {i+1}/{ticks}")

        # Show LFI summaries
        for region_id, lfi in mesh._lfis.items():
            field = lfi.get_field()
            if field and field.all_points():
                typer.echo(f"  LFI {region_id}:")
                typer.echo(f"    Points: {len(field.all_points())}")
                typer.echo(f"    Gen: {field.total_generation_mw():.1f} MW")
                typer.echo(f"    Con: {field.total_consumption_mw():.1f} MW")

        # Show GH summary
        gh = mesh.get_gh()
        if gh:
            summary = gh.get_global_summary()
            typer.echo(f"\n  GH Global:")
            typer.echo(f"    Kardashev: {summary['kardashev_index']:.4f}")
            typer.echo(f"    Trajectory alignment: {summary['trajectory_alignment']:.2%}")
            typer.echo(f"    Global efficiency: {summary['global_efficiency']:.4f}")

        time.sleep(0.5)

    typer.echo("\nMesh demo complete.")


@app.command()
def status(
    region: str = typer.Option(
        None,
        "--region", "-r",
        help="Filter by region ID",
    ),
    json_output: bool = typer.Option(
        False,
        "--json", "-j",
        help="Output as JSON",
    ),
) -> None:
    """Show status of ACNL mesh (simulation)."""
    # This would connect to a running mesh in production
    status_data = {
        "status": "simulated",
        "message": "No live mesh connected. Use 'demo' or 'mesh-demo' to run simulations.",
        "region_filter": region,
    }

    if json_output:
        typer.echo(json.dumps(status_data, indent=2))
    else:
        typer.echo("ACNL Status")
        typer.echo("-" * 30)
        for k, v in status_data.items():
            if v is not None:
                typer.echo(f"  {k}: {v}")


@app.command()
def tensor_demo(
    region: str = typer.Option(
        "earth/demo",
        "--region", "-r",
        help="Region ID",
    ),
) -> None:
    """Demo tensor-native field operations."""
    from ..core.ids import compute_node_id, plant_id
    from ..core.fields import STANDARD_COMPUTE_FEATURES
    from ..integration.sensors import generate_simulated_assertions
    from ..store.event_store import EventStore
    from ..mesh.aggregator import LocalFieldBuilder, AggregatorConfig
    from ..control.lfi import LocalFieldIntegrator
    from ..control.policies import DefaultTauLimitPolicy

    typer.echo("ACNL Tensor Demo")
    typer.echo("=" * 50)

    # Setup
    store = EventStore()
    builder = LocalFieldBuilder(AggregatorConfig(region_id=region))
    lfi = LocalFieldIntegrator(store, builder, DefaultTauLimitPolicy(), region)

    # Generate data
    assertions = generate_simulated_assertions(
        region_id=region,
        plant_count=3,
        compute_count=5,
    )
    for a in assertions:
        store.add_assertion(a)
        builder.ingest(a)

    lfi.rebuild_field()
    field = lfi.get_field()

    if field is None:
        typer.echo("No field data available.")
        return

    # Export as tensor
    typer.echo(f"\nField with {len(field.all_points())} points")
    typer.echo(f"Features: {STANDARD_COMPUTE_FEATURES}")

    ids, tensor = field.as_tensor(STANDARD_COMPUTE_FEATURES)
    typer.echo(f"\nTensor shape: {tensor.shape}")
    typer.echo(f"Tensor dtype: {tensor.dtype}")

    typer.echo("\nTensor contents:")
    for i, entity_id in enumerate(ids):
        row = tensor[i]
        typer.echo(f"  {entity_id}:")
        for j, feature in enumerate(STANDARD_COMPUTE_FEATURES):
            typer.echo(f"    {feature}: {row[j]:.4f}")

    # Show efficiency ranking
    typer.echo("\nEfficiency ranking (low carbon, high reliability):")
    efficient = field.sorted_by_efficiency()
    for i, point in enumerate(efficient[:5]):
        typer.echo(f"  {i+1}. {point.subject} (carbon: {point.carbon_intensity:.0f}, "
                  f"reliability: {point.reliability:.2f})")


@app.command()
def version() -> None:
    """Show ACNL version."""
    from .. import __version__
    typer.echo(f"ACNL v{__version__}")


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
