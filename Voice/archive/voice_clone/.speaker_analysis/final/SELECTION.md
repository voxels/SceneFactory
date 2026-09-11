# Audio-only speaker selection

All source analysis was performed from `input/candidates/audio_only`. Video
streams were not used.

## Gage status

- No Gage clip is currently accepted.
- The user rejected the first two machine-selected candidates; they are stored
  under `quarantine/rejected_by_user` and used as explicit non-Gage negatives.
- Two recalibrated candidates are stored under `review/gage_round2` for human
  confirmation.

## Ryan

The TikTok interval 6.060-9.200 was enrolled as the known Ryan reference.
The user confirmed the selected long-recording segment as Ryan. It is stored
under `accepted/ryan` and is now part of Ryan's enrollment set.

## Quarantine

All other detected speech—including music, background media, overlapping or
short speech, contradictory verifier results, and other voices—is stored under
`quarantine/bad_data`. Obsolete forced-cluster runs are kept separately under
`.speaker_analysis/quarantine/obsolete_runs` and must not be used for training.
