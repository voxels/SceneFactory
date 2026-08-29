# Scene Factory Master Workflow Checklist

This document is the authoritative checklist for the requirements discussed in the Ad2184 workflow chat.

Status terms:

- **Verified**: A current output or test proves the result.
- **Implemented**: Code or configuration exists, but the final production result is not yet proved.
- **Partial**: Some required parts exist.
- **Missing**: The required part does not exist.
- **Decision needed**: A user choice is necessary before the work can continue safely.

## A. Application and project structure

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| A01 | Scene Factory must live outside the source-media hierarchy. | Independent root: `/Users/voxels/SceneFactory`. Ad2184 remains an example project. | Verified | The application runs without moving the source media. |
| A02 | All source and model pointers must be flexible, with useful local defaults. | `examples/ad2184/project.json` contains `path_defaults` and uses named pointers. | Implemented | A second project can replace all roots without a code edit. |
| A03 | A new project must accept foreground characters, background characters, environments, scripts, and motion references. | Project and concept schemas cover these groups. The reusable drop-folder intake is not complete. | Partial | One new sample project is built only from the documented intake folders and JSON files. |
| A04 | The script and shot list must use a checked JSON schema. | Project, script, and concept schemas exist. | Implemented | Invalid IDs, durations, references, and formations fail with clear messages. |
| A05 | The first-use procedure must be clear and ordered. | `docs/02_QUICK_START.md` and `docs/06_OPERATOR_MANUAL.md` exist. | Partial | The guide matches the current CLI and current outputs with no stale statements. |

## B. Local models and ComfyUI

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| B01 | Use core ComfyUI, not LTX Desktop, as the generation host. | Current workflow targets `http://127.0.0.1:8188`. LTX Desktop is only a local weight source. | Implemented | A complete video job runs in core ComfyUI with LTX Desktop closed. |
| B02 | Consolidate model visibility across the local model trees. | Extra model paths expose shared ComfyUI models and local LTX 2.5 weights. | Partial | ComfyUI preflight reports no missing required model and the UI lists each required model once. |
| B03 | Use FLUX.2 Klein for image and key-frame generation. | `project.json` selects FLUX.2 Klein 4B distilled. Comfy image graphs exist. | Implemented | A fixed reference set produces an approved identity grid and storyboard grid. |
| B04 | Use Qwen for vision captions, prompt planning, and replaceable text conditioning. | Qwen3.5-9B completed 45 structured caption records. A local Qwen encoder is used in the native graph design. | Partial | Caption quality and LTX text-conditioning quality both pass visual review. |
| B05 | Use local LTX 2.5 for image-to-video generation. | Native core-ComfyUI LTX 2.5 API graphs exist. | Implemented | One 5-second and one 10-second portrait clip complete and play correctly. |
| B06 | Do not require broken LTX custom-node packages. | The native graph uses core ComfyUI LTX nodes. Two optional custom packages still fail to import. | Implemented | A full generation run succeeds without either optional package. |
| B07 | Document the CLI and show incremental output. | Caption execution prints per-image progress. General queue monitoring and the current command reference need one ordered guide. | Partial | The operator can see queued, running, completed, failed, and saved-output events for every stage. |

## C. Source intake, captions, face identity, and masks

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| C01 | Index all source images without changing them. | The source catalog indexes 45 K images by path and SHA-256. | Verified | Re-indexing reports the same 45 fingerprints. |
| C02 | Make structured Qwen captions for later training. | 45 raw responses and 45 validated JSON results exist. Caption audit reports 45 valid and 0 invalid. | Verified | Human review confirms the corrected labels. |
| C03 | Use the `k0l3k4` identity tag on every approved K training record. | The caption policy adds the identity tag. | Implemented | Dataset audit reports zero missing or conflicting K identity tags. |
| C04 | Use controlled attribute tags. | Current model output contains many duplicate and inconsistent tag forms. | Missing | All approved records use one controlled vocabulary and no free-form duplicates. |
| C05 | Classify visible life stage without inferring exact age. | The current template incorrectly forces `young adult, mid-20s` on all 45 records. | Missing | Each image has a reviewed apparent-life-stage label or `uncertain`; no exact age is inferred. |
| C06 | Detect all faces in each image. | The guide mentions this stage, but no pipeline command or output contract exists. | Missing | Each image has a face list, face boxes, confidence, and model provenance. |
| C07 | Match only K by face identity. | No implemented face-identity stage exists. | Missing | Multiple approved K anchor faces are used; uncertain matches are rejected or sent to manual review. |
| C08 | Make a full-subject mask after the K face is selected. | The guide mentions a face or subject mask, but no mask artifact exists. | Missing | Each group image has an approved K face match, full-person mask, isolated image, and overlay preview. |
| C09 | Prevent group originals from entering identity training. | Caption policy marks 32 images for isolation or rejection, but dataset approval does not yet enforce a mask artifact. | Partial | Dataset build rejects every multi-person record without an approved isolation record. |
| C10 | Keep mask, crop, caption, and source evidence connected. | No derivative provenance record exists. | Missing | Each derivative stores source hash, mask hash, crop coordinates, selected face ID, match score, and review state. |

## D. K0l3k4 character definition and training balance

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| D01 | Separate identity truth from generated candidate art. | Generated audition sheets are review material and are not allowed as training sources. | Implemented policy | Dataset manifest contains only user-source or approved isolated user-source images. |
| D02 | Define fixed identity traits separately from production variables. | The concept registry has broad stable and variable lists, but no complete controlled character contract. | Partial | One reviewed K contract defines facial structure, body proportions, target life stage, and identity continuity without wardrobe or environment entanglement. |
| D03 | Keep hair presentation, makeup, expression, wardrobe, pose, camera, light, and background variable. | Current captions store some of these, but not with one vocabulary. | Partial | Balance report shows coverage for every variable group. |
| D04 | Keep identity, hero wardrobe, visual style, and environment as separate concepts. | Identity is separate. Wardrobe and style are still embedded in project prompt tags. | Partial | Each repeating concept has a separate token or reference contract and an independent validation grid. |
| D05 | Balance framing. | Current Qwen labels: 15 close-ups, 1 medium close-up, 28 medium shots, and no reliable full-body class. | Missing balance | Approved set meets target counts for face, head-and-shoulders, waist-up, three-quarter, and full-body views. |
| D06 | Balance view and camera angle. | Current labels are about 40 frontal views and have almost no reliable profile or three-quarter coverage. | Missing balance | Approved set includes front, left and right three-quarter, left and right profile, and useful back or body views. |
| D07 | Balance expression. | Current labels contain about 41 smiling images and very few neutral images. | Missing balance | Neutral, slight smile, full smile, determined, and action expressions meet target ranges. |
| D08 | Balance life stage for the selected final K build. | The source set spans multiple visible life stages. The target reference cluster is not approved. | Decision needed | The user approves one adult reference cluster for the production K build; other life stages are held out or trained separately. |
| D09 | Balance wardrobe and hair without teaching one outfit as identity. | Source images contain many outfits and hair states. Production prompts currently bind one runner outfit to the character. | Partial | Identity captions describe visible variable states; the runner wardrobe is validated as a separate production concept. |
| D10 | Use enough training and validation images. | 45 sources exist. Only 13 are directly usable before isolation. Minimum approved training count is 24. | Blocked | At least 24 approved training images and a separate validation set pass identity and leakage checks. |
| D11 | Train and validate a FLUX.2 Klein identity LoRA. | Concept state is `planned`; no trained weight or promotion record exists. | Missing | LoRA passes fixed seeds, views, expressions, clothing changes, body views, and allowed LoRA-stack tests. |

## E. Character candidates and character sheets

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| E01 | Generate many K identity candidates with different seeds, poses, and clothes. | A six-panel visual audition sheet exists. Four numbered Comfy candidate variants are compiled. | Partial | Candidate outputs are saved with seed, prompt, reference set, and review decision. |
| E02 | Make a complete K character sheet. | Plans include front, three-quarter, profiles, full front, full back, expressions, and wardrobe. | Implemented plan | One approved identity produces a complete, internally consistent sheet. |
| E03 | Use at least three POV or camera alternatives for each scene. | The script compiles three formations per shot and four seed candidates. | Implemented plan | Each shot has at least three visually distinct, approved camera formations. |
| E04 | Add the man from the supplied photos as one automaton worker. | A four-panel male worker audition sheet exists. Original source-copy provenance is not complete. | Partial | His source images are stored, labeled, reviewed, and connected to a worker concept without changing K. |

## F. Storyboards, key frames, environments, and clips

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| F01 | Build storyboards from the shot-list JSON. | Storyboard graphs and a full visual graph manifest exist. | Implemented | Each storyboard frame is saved and linked to scene, shot, formation, seed, and prompt. |
| F02 | Build character images before environment shots. | The intended order is documented, but current execution gates do not fully enforce it. | Partial | Environment generation cannot start until approved character sheets and storyboard blocking exist. |
| F03 | Make production key frames for every scene and at least three POVs. | 84 storyboard variants are compiled from 21 formations and 4 candidates. | Implemented plan | Approved production key frames exist for every required formation. |
| F04 | Direct animation with approved key frames. | LTX image-to-video graphs use staged key frames and motion text. | Implemented plan | Clip metadata records key-frame hash, motion direction, seed, frame count, and output. |
| F05 | Accept video as choreography input. | The Apple 1984 reference is configured for motion and cut timing only. | Implemented policy | The system extracts or records timing, camera motion, and action cues without using the video for identity. |
| F06 | Generate portrait 9:16 clips. | Current project format and native video graphs use portrait dimensions. | Implemented | Saved clips report 9:16 dimensions and play with no rotation or crop error. |
| F07 | Generate 5-second slow-motion-direction clips. | 5-second variants are compiled with controlled slow movement. | Implemented plan | At least one approved 5-second clip completes and matches the intended pace. |
| F08 | Generate 10-second fast-paced clips. | 10-second variants are compiled with urgent movement. | Implemented plan | At least one approved 10-second clip completes and matches the intended pace. |
| F09 | Make many clips for later edit-duration changes. | 168 video tasks are compiled. | Implemented plan | All required clips have complete outputs, failure records, and retry records. |
| F10 | Assemble extended sequences with continuity. | Sequence plans exist. No final sequence has been generated. | Missing output | One full scene sequence passes identity, wardrobe, environment, direction, timing, and continuity review. |

## G. Execution, outputs, monitoring, and proof

| ID | Requirement | Connection and evidence | Status | Acceptance condition |
|---|---|---|---|---|
| G01 | Save intermediate outputs in clear folders. | Caption, graph, and some generated-image folders exist. A single output map is not current. | Partial | The operator guide lists every input, intermediate output, final output, and log folder. |
| G02 | Show visual output before semantic refinement. | K and worker audition sheets plus some storyboard images exist. | Partial | The user can open all current visual artifacts from one review index. |
| G03 | Continuously monitor execution and apply reusable fixes. | ComfyUI can be monitored, but there is no durable run ledger for all stages. | Missing | Every job records queued, running, complete, failed, retry, model, seed, prompt, and output states. |
| G04 | Continue until a full graph and one complete generation cycle exist. | Graph generation is largely complete. A full identity-LoRA-to-sequence cycle is not complete. | Missing | One K dataset, LoRA, character sheet, storyboard set, key-frame set, 5-second clip, 10-second clip, and assembled sequence all pass review. |
| G05 | Test future reuse. | Five caption regression tests previously passed. Current graph and video execution are not end-to-end tested. | Partial | Automated tests plus one clean sample-project run pass from intake through saved clip. |
| G06 | Keep documentation ordered, cross-referenced, summarized, and cited. | Nine documents exist, but several status statements are stale and the full chat checklist was absent. | Partial | This checklist is linked from the documentation index; all status documents agree with current evidence. |

## H. Immediate blocking order

1. Add the face-detection, K face-match, full-subject-mask, and isolated-derivative stage.
2. Remove the forced `mid-20s` caption text and add reviewed apparent-life-stage metadata.
3. Make the controlled K character-label contract and balance report.
4. Isolate or reject the 32 group images.
5. Select the final adult reference cluster for K.
6. Approve at least 24 training images and a separate validation set.
7. Train and validate the K FLUX.2 Klein LoRA.
8. Generate and approve the complete K character sheet.
9. Generate and approve the storyboard and production key frames for all formations.
10. Run one 5-second and one 10-second LTX 2.5 portrait clip.
11. Assemble one complete scene sequence.
12. Update all guides and run the clean manual verification procedure.

## I. Current evidence summary

- Source images indexed: 45.
- Structured caption results: 45 valid, 0 invalid.
- Directly usable before isolation: 13.
- Need isolation or rejection: 32.
- Human-reviewed captions: 0.
- Approved LoRA training set: 0.
- Trained K identity LoRA: 0.
- Compiled character-sheet graphs: 36.
- Compiled storyboard graphs: 84.
- Compiled portrait video tasks: 168.
- Completed native LTX 2.5 clips: 0.
- Completed full generation cycles: 0.

The generated audition sheets are useful visual references. They are not proof of a trained identity and must not be used as identity training sources.
