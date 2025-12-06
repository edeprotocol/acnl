import time
import json
from typing import Optional

# Optional typer import - gracefully handle if not installed
try:
    import typer
    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False
    typer = None

from sfl.mesh.lfi import LocalFieldIntegrator, LFIConfig
from sfl.mesh.rc import RegionalCoordinator, RCConfig
from sfl.mesh.gh import GlobalHarmonizer, GHConfig
from sfl.integrations.sensors import generate_simulated_assertions


def create_app():
    """Create the typer app if available."""
    if not TYPER_AVAILABLE:
        raise RuntimeError("typer is required for CLI. Install with: pip install typer")
    return typer.Typer(name="mesh", help="Energy-Compute Fractal Mesh CLI")


# Create app lazily
_app = None


def get_app():
    global _app
    if _app is None:
        _app = create_app()
    return _app


def lfi_command(
    region_id: str = "earth/eu-fr-1",
    tick_ms: int = 1000,
    horizon_ms: int = 5000,
    simulate: bool = True,
):
    """Run a Local Field Integrator."""
    if not TYPER_AVAILABLE:
        print("typer is required for CLI. Install with: pip install typer")
        return

    config = LFIConfig(
        region_id=region_id,
        tick_interval_ms=tick_ms,
        field_horizon_ms=horizon_ms,
    )

    lfi = LocalFieldIntegrator(config)

    print(f"Starting LFI for region: {region_id}")
    print(f"Tick interval: {tick_ms}ms, Field horizon: {horizon_ms}ms")

    try:
        while True:
            # Ingest simulated data if enabled
            if simulate:
                assertions = generate_simulated_assertions(
                    region_id=region_id,
                    num_compute_nodes=3,
                    num_plants=1,
                    num_lines=2,
                )
                lfi.ingest_assertions(assertions)

            # Run tick
            lfi.tick()

            # Print status
            field = lfi.get_field()
            tau_limits = lfi.get_tau_limits()

            if field:
                print(f"\n[{field.generated_at_ms}] Field: {len(field.points)} points")
                print(f"  Available power: {field.total_available_power():.1f} MW")
                print(f"  Avg carbon: {field.avg_carbon_intensity():.1f} gCO2/kWh")
                print(f"  Tau limits: {json.dumps({k: round(v, 3) for k, v in tau_limits.items()})}")

            time.sleep(tick_ms / 1000.0)

    except KeyboardInterrupt:
        print("\nStopping LFI...")


def demo_command():
    """Run a full demo with LFI -> RC -> GH hierarchy."""

    region_id = "earth/eu-fr-1"

    # Create LFI
    lfi = LocalFieldIntegrator(LFIConfig(region_id=region_id))

    # Create RC
    rc = RegionalCoordinator(
        RCConfig(region_id="earth/eu", carbon_budget_gco2_per_hour=500_000),
        lfi_ids=[region_id],
    )

    # Create GH
    gh = GlobalHarmonizer(
        GHConfig(global_carbon_budget_gco2_per_hour=10_000_000),
        rc_ids=["earth/eu"],
    )

    print("Starting Energy Mesh Demo")
    print("=" * 50)

    try:
        tick = 0
        while True:
            tick += 1

            # 1. Ingest sensor data
            assertions = generate_simulated_assertions(region_id, 3, 1, 2)
            lfi.ingest_assertions(assertions)

            # 2. LFI tick
            lfi.tick()

            # 3. RC tick (every 5 LFI ticks)
            if tick % 5 == 0:
                lfi_field = lfi.get_field()
                if lfi_field:
                    rc.update_lfi_field(region_id, lfi_field)
                rc.update_lfi_summary(region_id, lfi.get_summary())
                rc.tick()

                # Push constraints back to LFI
                lfi.set_regional_constraints(rc.get_constraints())

            # 4. GH tick (every 30 ticks)
            if tick % 30 == 0:
                gh.update_rc_summary("earth/eu", rc.get_summary())
                gh.tick()

                # Push params to RC
                rc.set_global_params(gh.get_global_params())

            # Print status
            print(f"\n--- Tick {tick} ---")

            field = lfi.get_field()
            if field:
                print(f"LFI [{region_id}]:")
                print(f"  Points: {len(field.points)}, Available: {field.total_available_power():.1f} MW")
                print(f"  Tau limits: {lfi.get_tau_limits()}")

            if tick % 5 == 0:
                print(f"RC [earth/eu]:")
                print(f"  Constraints: {rc.get_constraints()}")

            if tick % 30 == 0:
                print(f"GH [global]:")
                print(f"  State: {gh.get_global_state()}")
                print(f"  Params: {gh.get_global_params()}")

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping demo...")


# Register commands if typer is available
if TYPER_AVAILABLE:
    app = get_app()

    @app.command()
    def lfi(
        region_id: str = typer.Option("earth/eu-fr-1", help="Region ID"),
        tick_ms: int = typer.Option(1000, help="Tick interval in ms"),
        horizon_ms: int = typer.Option(5000, help="Field horizon in ms"),
        simulate: bool = typer.Option(True, help="Use simulated sensors"),
    ):
        """Run a Local Field Integrator."""
        lfi_command(region_id, tick_ms, horizon_ms, simulate)

    @app.command()
    def demo():
        """Run a full demo with LFI -> RC -> GH hierarchy."""
        demo_command()


def main():
    """Main entry point."""
    if TYPER_AVAILABLE:
        get_app()()
    else:
        print("typer is required for CLI. Install with: pip install typer")
        print("Alternatively, you can import and use the functions directly:")
        print("  from sfl.mesh.cli import demo_command")
        print("  demo_command()")


if __name__ == "__main__":
    main()
