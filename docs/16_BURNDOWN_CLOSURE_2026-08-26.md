# Production burn-down closure

Date: 2026-08-26  
Authority: this file supersedes stale completion claims in earlier status and handoff documents.  
Machine-readable authorities: `examples/ad2184/build/reference/contracts/index.json`, `examples/ad2184/build/reference/disagreement_report.json`, `examples/ad2184/build/tracking/tracking_manifest.json`, and `examples/ad2184/build/invalidation_state.json`.

## Outcome

The contract, disagreement-gate, descendant-invalidation, screen-tracking, real K-pose, and reconstruction-tooling work is implemented and tested. A production render is intentionally still blocked. Two external gates cannot be completed by the agent: acceptance/download of the gated LTX motion-control license and user approval of production artifacts. The official SAM3 checkpoint also remains incomplete after its transfer slowed to an approximately 80-minute estimate; its resumable partial and executable workflow are preserved.

## Original list, closed against evidence

| # | State | Result and evidence |
|---:|---|---|
| 1 | Complete | All 21 reference tasks are populated in `build/reference/contracts/index.json`. Records identify direct interactive multimodal review and do not falsely claim local Qwen execution. |
| 2 | Complete | Fourteen derived contracts cover wardrobe, group, hammer, environment, camera, lighting, blocking, and screen state. Every observed field carries frame path, SHA-256, timestamp, shot, and task provenance. |
| 3 | Complete | `reference_contracts.py` audits written claims against derived evidence. `compile` and `comfy-build` reject incomplete, contradictory, or stale audits. Current audit: 25 claims, zero unresolved contradictions, allowed. |
| 4 | Complete, QC pending | Official SDPose ran on the real reference from 36.48 through 39.48 seconds at 24 fps. It emitted 73 OpenPose frames, one person per frame. Association, confidence filtering, EMA smoothing, and root-relative retargeting produced 39 usable control frames. No joints were synthesized. See `build/tracking/k_body_pose_raw.json` and `build/tracking/shot_03_to_05/k_body_pose.json`. |
| 5 | Complete at preflight | Official LTX nodes load and the video-only 73-point IC-LoRA API graph validates. CLI gated access was confirmed and the motion weight was downloaded with verified SHA-256 `e279807ee3aa3db1ce60188d665ff83342860367dcd6bac19f8bd5a99a9e1dca`. The official LTX-2.5 motion-track workflow intentionally uses this 2.3-named IC-LoRA with the LTX-2.5 distilled transformer. Runtime audit reports `ready: true` with zero blockers. A production render remains separately gated by masks and user approvals. |
| 6 | Partial after real inference | Eighty-four proxy PGM masks and rigid centroid/rotation samples exist. The official SAM3.1 checkpoint is installed and verified with SHA-256 `9ba99c92703c2e8b4f47de2d34a539bb8e18923049e238b780d70dbe6368eb03`. Three real 59-frame passes were executed: memory tracking retained 3 frames; per-frame box refinement retained 21; text-plus-box detection emitted 59 nonempty masks but visibly produced false positives after the reference cuts away from the hammer. None is promoted. See `build/tracking/shot_06/sam3_attempt_report.json`. Manual roto/corrected per-frame boxes and user QC remain necessary. |
| 7 | Complete, QC pending | A four-corner normalized screen homography with hashed source provenance exists. Last intact is 46.04 seconds; first destroyed is 46.08 seconds, one 25 fps frame later. See `build/tracking/shot_06/speaker_screen_corners.json`. |
| 8 | Blocked by 5, 6, 11 | No production master or alternate clip is claimed. The reconstruction queue contains 152 jobs: 124 required; 68 input-ready; 56 blocked. Rendering before the control weight, semantic hammer masks, and user approvals would violate the generation gates. |
| 9 | Partial | A real BiRefNet source matte and RGBA foreground exist in `build/proofs/real_birefnet_matte/`; hashes and scope are in `proof_manifest.json`. A no-audio synthetic layered/green-insert proof exists in `build/proofs/compositor_smoke/`. Neither is falsely labeled as a production reconstruction. |
| 10 | Complete | Runtime fingerprints now invalidate all transitive contract, track, layer, and artifact descendants. First compile invalidated 274 nodes; an unchanged second compile invalidated zero. |
| 11 | User action required | Only the user can approve artifacts. No approval was fabricated. The system requires `decision: approved`, `approved_by: user`, and an empty issue list. |

## Runtime and models established

- Repaired official `ComfyUI-LTXVideo`; incompatible Mattabyte registry was moved to `disabled_custom_nodes` with backups retained.
- Core ComfyUI, official LTX, SDPose, SAM3, BiRefNet, RT-DETR, VideoHelperSuite, and the project pose/mask output nodes import.
- Verified checkpoints: SDPose SHA-256 `63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721`; RT-DETR `581f9af9bbabb664d1891cbccd823308b176ecd409146f954dfa39af3bec2476`; BiRefNet `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154`.
- The entire pipeline remains visual-only. Audio is ignored, unmapped, and never generated.

## Resume commands

The gated LTX motion weight is installed and verified. Runtime evidence is `examples/ad2184/build/comfyui/ltx_runtime_audit.json`.

SAM3 and the LTX motion LoRA are now installed. Review `sam3_attempt_report.json`, manually correct/roto the missing visible-hammer frames, and ensure frames after the edit away from the hammer are empty. Then review the K skeleton, screen corners, destruction boundary, and real matte before supplying user approvals. Only then run the reference-faithful master and narrative-bounded alternate queue.

## Verification

`python3 -m unittest discover -s tests -v`: **59 tests passed**.
