# USDZ ingestion and avatar processing

The modeling-interview example now has an auditable USDZ stage. `ingest-usdz`
enumerates every archive member, records member SHA-256 hashes, inspects textual USD
layers and binary USDC through the installed OpenUSD `usdcat`, and binds each source
hash to the canonical control render manifest. The current three captures yield 12
hashed members and 168 controls (RGB, alpha, silhouette, metric/normalized depth,
normals, and lineart).

The source scans are static captures: the ingestion report explicitly records that no
embedded skeleton, blend-shape, or animation data was found. That is important—those
features are not inferred merely because a USDZ exists.

The fallback delivery adapter imports the high-resolution portrait capture in Blender,
creates a deterministic head/neck/jaw/eye rig, generates bounded facial and viseme
blend shapes, exports a textured/normals/UV-preserving USDZ, and derives a matching
binary Gaussian PLY from the same mesh vertices. `validate-avatar` checks archive
contents, hashes, PLY schema, and vertex count. The generated artifacts are delivery
prototypes until voice/viseme timing and a runtime backend are bound.

Unreal Engine 5.8 is the preferred final authoring/runtime backend and is now
installed at `/Users/Shared/Epic Games/UE_5.8` (5.8.2, changelist 56702186). The
installed build contains the required Control Rig, Live Link, RigLogic, USD
Importer, MetaHuman, and Apple ARKit plugin manifests. The machine-readable
contract is recorded in `build/pipeline/preflight.json`.

The editor/render path is currently held by an environment issue, not by the
USDZ asset: macOS 27 is using `/Applications/Xcode-beta.app`, whose `metal`
executable reports `cannot execute tool 'metal' due to missing Metal Toolchain`.
Install the component explicitly with
`xcodebuild -downloadComponent MetalToolchain`, rerun preflight, and only then
launch the editor. While rendering is held, use the editor-independent binary
for bounded checks with `UnrealEditor-Cmd -nullrhi -unattended -nop4 -nosplash
-nosound`; this does not prove a Metal render or native visionOS Persona/
SharePlay runtime. The Blender adapter remains available only for conversion and
canonical render fallbacks. Native Persona fidelity is not claimed without a
runtime test on the supported Apple delivery path.
