"""Named RIP / RIP-X configurations and scenario ``rip`` objects.

Timers are in simulation rounds. ``rip`` scales the RFC 2453 timers
(30 s updates, 180 s timeout, 120 s garbage collection) down by six so one
round stands for five seconds.
"""

from __future__ import annotations

from typing import Any

from ripx.routing.metrics import cost_policy_from_config
from ripx.routing.scheduling import schedule_from_config

PROFILES: dict[str, dict[str, Any]] = {
    # The simulator's original behavior: every router floods every round.
    "baseline": {},
    # Standard RIP with scaled RFC timers.
    "rip": {
        "updates": {"type": "fixed", "interval": 5},
        "route_timeout": 30,
        "garbage_collection": 20,
    },
    # RIP-X: adaptive periodic updates, route requests on loss and
    # congestion-aware link costs, with the same timers as "rip".
    "ripx": {
        "updates": {"type": "adaptive", "min_interval": 5, "max_interval": 20, "growth": 2},
        "request_on_loss": True,
        "metric": {"type": "congestion_aware"},
        "route_timeout": 30,
        "garbage_collection": 20,
    },
}

_BOOLEAN_KEYS = ("split_horizon", "poison_reverse", "triggered_updates", "request_on_loss")
_INTEGER_KEYS = ("route_timeout", "garbage_collection")
_KNOWN_KEYS = {"profile", "updates", "metric", *_BOOLEAN_KEYS, *_INTEGER_KEYS}


def resolve_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a ``rip`` object over the profile it names (default ``baseline``)."""
    config = dict(config or {})
    unknown = set(config) - _KNOWN_KEYS
    if unknown:
        raise ValueError(f"unknown rip settings: {', '.join(sorted(unknown))}")
    profile = config.pop("profile", "baseline")
    if profile not in PROFILES:
        raise ValueError(f"rip.profile must be one of: {', '.join(PROFILES)}")
    merged = {**PROFILES[profile], **config}
    for key in _BOOLEAN_KEYS:
        if key in merged and not isinstance(merged[key], bool):
            raise ValueError(f"rip.{key} must be true or false")
    for key in _INTEGER_KEYS:
        if key in merged and (not isinstance(merged[key], int) or merged[key] < 1):
            raise ValueError(f"rip.{key} must be a positive integer")
    for key in ("updates", "metric"):
        if key in merged and not isinstance(merged[key], dict):
            raise ValueError(f"rip.{key} must be an object")
    return {"profile": profile, **merged}


def network_options(config: dict[str, Any] | None) -> dict[str, Any]:
    """Translate a ``rip`` object into ``RipNetwork`` keyword arguments.

    Each call builds a fresh schedule, because adaptive schedules hold
    per-router state.
    """
    resolved = resolve_config(config)
    options: dict[str, Any] = {key: resolved[key] for key in (*_BOOLEAN_KEYS, *_INTEGER_KEYS) if key in resolved}
    options["schedule"] = schedule_from_config(resolved.get("updates"))
    options["cost_policy"] = cost_policy_from_config(resolved.get("metric"))
    return options


def describe_options(options: dict[str, Any], profile: str | None = None) -> dict[str, Any]:
    """JSON-friendly view of the options a network was built with."""
    described = {} if profile is None else {"profile": profile}
    described |= {key: value for key, value in options.items() if key not in {"schedule", "cost_policy"}}
    described["updates"] = options["schedule"].describe()
    described["metric"] = options["cost_policy"].describe()
    return described
