"""Tests for ACNL core events."""

import pytest
from acnl.core.ids import plant_id, compute_node_id, lfi_id, Coord
from acnl.core.observables import EnergyObservableKind, Observable, UNIT_MW
from acnl.core.events import (
    Assertion,
    Claim,
    Challenge,
    Proof,
    ComputeEvent,
)


class TestAssertion:
    """Test Assertion events."""

    def test_assertion_creation(self):
        coord = Coord.now("earth/us/west")
        observable = Observable(
            kind=EnergyObservableKind.GENERATION_POWER,
            value=100.0,
            unit=UNIT_MW,
        )
        assertion = Assertion.create(
            issuer=lfi_id("earth/us/west"),
            subject=plant_id("solar-1"),
            coord=coord,
            observable=observable,
        )
        assert assertion.subject == "plant:solar-1"
        assert assertion.observable.value == 100.0
        assert assertion.assertion_id is not None


class TestClaim:
    """Test Claim events."""

    def test_claim_creation(self):
        coord = Coord.now("earth/us/west")
        claim = Claim.create(
            claimant=compute_node_id("gpu-1"),
            subject=compute_node_id("gpu-1"),
            coord=coord,
        )
        assert claim.claimant == "compute-node:gpu-1"
        assert len(claim.assertions) == 0

    def test_claim_add_assertion(self):
        coord = Coord.now("earth/us/west")
        claim = Claim.create(
            claimant=compute_node_id("gpu-1"),
            subject=compute_node_id("gpu-1"),
            coord=coord,
        )

        assertion = Assertion.create(
            issuer=lfi_id("earth/us/west"),
            subject=compute_node_id("gpu-1"),
            coord=coord,
            observable=Observable(
                kind=EnergyObservableKind.CONSUMPTION_POWER,
                value=50.0,
                unit=UNIT_MW,
            ),
        )
        claim.add_assertion(assertion)
        assert len(claim.assertions) == 1


class TestChallenge:
    """Test Challenge events."""

    def test_challenge_creation(self):
        coord = Coord.now("earth/us/west")
        challenge = Challenge.create(
            challenger=lfi_id("earth/us/west"),
            target=compute_node_id("gpu-1"),
            coord=coord,
            challenge_type="power_correlation",
            payload={"workload": "benchmark-v1"},
        )
        assert challenge.target == "compute-node:gpu-1"
        assert challenge.challenge_type == "power_correlation"
        assert challenge.status == "pending"


class TestProof:
    """Test Proof events."""

    def test_proof_creation(self):
        coord = Coord.now("earth/us/west")
        proof = Proof.create(
            challenge_id="challenge-12345",
            responder=compute_node_id("gpu-1"),
            coord=coord,
            result={"power_measured_mw": 48.5, "duration_ms": 1000},
        )
        assert proof.challenge_id == "challenge-12345"
        assert proof.responder == "compute-node:gpu-1"
        assert proof.result["power_measured_mw"] == 48.5


class TestComputeEvent:
    """Test ComputeEvent."""

    def test_compute_event_creation(self):
        coord = Coord.now("earth/us/west")
        event = ComputeEvent.create(
            pattern_id="pattern:llm-inference",
            compute_node_id=compute_node_id("gpu-1"),
            coord=coord,
            job_id="job-12345",
            tcu_used=100.0,
            energy_kwh=0.5,
            latency_ms=1500,
            success=True,
            info_gain_bits=1000.0,
        )
        assert event.pattern_id == "pattern:llm-inference"
        assert event.job_id == "job-12345"
        assert event.tcu_used == 100.0
        assert event.energy_kwh == 0.5
        assert event.success is True
        assert event.info_gain_bits == 1000.0

    def test_compute_event_efficiency(self):
        coord = Coord.now("earth/us/west")
        event = ComputeEvent.create(
            pattern_id="pattern:llm-inference",
            compute_node_id=compute_node_id("gpu-1"),
            coord=coord,
            job_id="job-12345",
            tcu_used=100.0,
            energy_kwh=0.5,
            latency_ms=1500,
            success=True,
            info_gain_bits=1000.0,
        )
        # efficiency = info_gain / energy = 1000 / 0.5 = 2000
        assert event.efficiency() == 2000.0

    def test_compute_event_efficiency_no_info_gain(self):
        coord = Coord.now("earth/us/west")
        event = ComputeEvent.create(
            pattern_id="pattern:llm-inference",
            compute_node_id=compute_node_id("gpu-1"),
            coord=coord,
            job_id="job-12345",
            tcu_used=100.0,
            energy_kwh=0.5,
            latency_ms=1500,
            success=True,
        )
        assert event.efficiency() == 0.0
