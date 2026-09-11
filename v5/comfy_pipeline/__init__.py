"""Comfy pipeline package — Cezar teaser execution layer (v5).

Metadata-layer implementation: validated workflow graphs, manifest schemas,
the identity-gate pre-filter, the refusal-with-redirection loop, and assembly
EDL generation. Nothing here generates video; his Mac executes the graphs.
"""

from .graphs import (
    load_workflow,
    validate_api_graph,
    instantiate_event_take,
    WORKFLOW_SPECS,
)
from .manifests import (
    validate_shot_manifest,
    build_take_record,
    build_review_record,
)
from .identity_gate import (
    load_impression,
    cosine_distance,
    gate_band,
    prefilter,
    HOLDS_MAX,
    DRIFTS_MAX,
)
from .redirection import (
    RefusalRecord,
    redirect,
    MAX_DEBUG_ATTEMPTS,
)
from .edl import build_edl

__all__ = [
    "load_workflow",
    "validate_api_graph",
    "instantiate_event_take",
    "WORKFLOW_SPECS",
    "validate_shot_manifest",
    "build_take_record",
    "build_review_record",
    "load_impression",
    "cosine_distance",
    "gate_band",
    "prefilter",
    "HOLDS_MAX",
    "DRIFTS_MAX",
    "RefusalRecord",
    "redirect",
    "MAX_DEBUG_ATTEMPTS",
    "build_edl",
]
