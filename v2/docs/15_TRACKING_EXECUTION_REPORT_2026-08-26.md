# Production tracking execution report

Date: 2026-08-26

This report covers burn-down items 4, 6, and 7. It is updated by [16_BURNDOWN_CLOSURE_2026-08-26.md](16_BURNDOWN_CLOSURE_2026-08-26.md). A record existing is not the same as that record being approved for generation. `build/tracking/tracking_manifest.json` is the machine-readable authority for readiness.

## K skeleton: real inference executed, user QC pending

The production orchestration now supports performer association by minimum center displacement then confidence, confidence filtering, exponential moving-average smoothing, and root-relative normalized retarget controls for K's proportions.

Apple Vision failed, so the production path was moved to the official Comfy-Org SDPose checkpoint. Real inference completed on 73 frames from 36.48–39.48 seconds at 24 fps. All input frames contain one detected person; 39 frames contain usable root-relative retarget controls after confidence filtering. The checked-in K records contain no fabricated joints and report the exact coverage.

Records:

- `examples/ad2184/build/tracking/shot_03/k_body_pose.json`
- `examples/ad2184/build/tracking/shot_04/k_body_pose.json`
- `examples/ad2184/build/tracking/shot_05/k_body_pose.json`

The SDPose checkpoint SHA-256 is `63d01f9a7494560693b24767f4469d59c9d3266b31ff0a253e74d1e611442721`. Next action is user QC and selection/interpolation policy for uncovered frames before promoting a generation track.

## Hammer: temporal records produced, semantic masks blocked

Frame-provenance observations establish:

- held by K through 43.40 seconds;
- ownership release boundary at approximately 43.44 seconds;
- first separately visible flight frame at 43.72 seconds;
- flight/impact track through the last intact screen frame at 46.04 seconds.

Eighty-four temporal masks plus centroid and rotation samples were written. They are rigid, manual-keyframe proxy masks and are explicitly not production-ready. The missing SAM checkpoint prevents claiming semantic temporal masks. They require user QC or replacement with SAM output.

Record: `examples/ad2184/build/tracking/shot_06/hammer_rigid_body.json`

## Projection screen: four-corner record and boundary produced

A four-corner screen annotation, unit-square-to-frame homography, source-frame hash, and frame-accurate destruction boundary were written:

- last intact frame: 46.04 seconds;
- first destroyed/blast frame: 46.08 seconds;
- source precision: one 25 fps frame, or 0.04 seconds.

The green insert exists through 46.04 seconds and begins shattering at 46.08 seconds. The annotation is operational for post and remains subject to user QC.

Record: `examples/ad2184/build/tracking/shot_06/speaker_screen_corners.json`

## Reproduction

```bash
cd /Users/voxels/SceneFactory
python3 v1/production_tracking.py v1/examples/ad2184
python3 -m unittest discover -s v1/tests -v
```

Verified result: 59 tests pass. The tracking manifest continues to block generation because semantic hammer masks and user approvals are not yet production-ready.
