"""SceneFactory ComfyUI app — v5 execution-layer node pack.

A ComfyUI custom-node pack implementing the A->B->C->D Cezar teaser pipeline
as an app surface, with voice capture as a first-class input and the
cross-media review UI the user directed ("a ui for follow up review to fine
tune references across media types maybe just as an app in comfy").

Alignment: v5/DESIGN_SPEC_COMFY_PIPELINE.md (sibling crew). Where the sibling
comfy_pipeline package is importable, node logic defers to it; otherwise each
node carries a pure-Python fallback so the pack loads standalone on the Mac.

Standing rules baked in:
- "Scene Factory owns manifests and approvals; ComfyUI executes generated
  API graphs." Approval/manifest writes are OUTPUT_NODEs owned here.
- USER ATTRIBUTION OVERRULES THE MODEL, no exceptions. The automated
  identity pre-filter is diagnostic: it may reject, never approve.
- A refusal must come with redirection: the refusal loop debugs rejected
  content into an acceptable request and retries (bounded), never stalls.
"""

from .node_types import (
    SF_IDENTITY, SF_ENV, SF_TAKE, SF_VOICE, SF_CANDIDATE,
    SF_REVIEW, SF_MANIFEST, SF_EDL, SF_REFUSAL,
)
from .nodes_workflow import (
    SF_IdentityReferenceIntake,
    SF_IdentityGatePrefilter,
    SF_EnvironmentReference,
    SF_EventTakeParams,
    SF_AssemblyHandoff,
)
from .nodes_voice import (
    SF_VoiceReferenceProfile,
    SF_VoiceParagraphRender,
    SF_VoiceListeningGate,
)
from .nodes_review import (
    SF_ReviewCandidateBrowser,
    SF_UserAttribution,
    SF_RefusalRedirect,
)
from .nodes_manifest import (
    SF_TakeManifestWriter,
    SF_GraphManifestBuilder,
)

NODE_CLASS_MAPPINGS = {
    # Workflow A-D
    "SF_IdentityReferenceIntake": SF_IdentityReferenceIntake,
    "SF_IdentityGatePrefilter": SF_IdentityGatePrefilter,
    "SF_EnvironmentReference": SF_EnvironmentReference,
    "SF_EventTakeParams": SF_EventTakeParams,
    "SF_AssemblyHandoff": SF_AssemblyHandoff,
    # Voice (first-class input)
    "SF_VoiceReferenceProfile": SF_VoiceReferenceProfile,
    "SF_VoiceParagraphRender": SF_VoiceParagraphRender,
    "SF_VoiceListeningGate": SF_VoiceListeningGate,
    # Review (user's eyes = final approval)
    "SF_ReviewCandidateBrowser": SF_ReviewCandidateBrowser,
    "SF_UserAttribution": SF_UserAttribution,
    "SF_RefusalRedirect": SF_RefusalRedirect,
    # Manifests / approvals (Scene Factory owns these)
    "SF_TakeManifestWriter": SF_TakeManifestWriter,
    "SF_GraphManifestBuilder": SF_GraphManifestBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SF_IdentityReferenceIntake": "SF Identity Reference Intake (A)",
    "SF_IdentityGatePrefilter": "SF Identity Gate Pre-filter (A)",
    "SF_EnvironmentReference": "SF Environment Reference (B)",
    "SF_EventTakeParams": "SF Event Take Params (C)",
    "SF_AssemblyHandoff": "SF Assembly Handoff (D)",
    "SF_VoiceReferenceProfile": "SF Voice Reference Profile",
    "SF_VoiceParagraphRender": "SF Voice Paragraph Render",
    "SF_VoiceListeningGate": "SF Voice Listening Gate",
    "SF_ReviewCandidateBrowser": "SF Review Candidate Browser",
    "SF_UserAttribution": "SF User Attribution (final approval)",
    "SF_RefusalRedirect": "SF Refusal Redirect",
    "SF_TakeManifestWriter": "SF Take Manifest Writer",
    "SF_GraphManifestBuilder": "SF Graph Manifest Builder",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
