#!/usr/bin/env python3
"""Audio-only Gage/Ryan candidate diarization with conservative review gates."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio
import whisper
from sklearn.cluster import KMeans

# SpeechBrain 1.0 expects an API removed from recent torchaudio releases.
if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["soundfile"]

from speechbrain.inference.speaker import EncoderClassifier  # noqa: E402


@dataclass
class Chunk:
    source: Path
    start: float
    end: float
    text: str
    embedding: np.ndarray
    rms_db: float
    score_gage: float = 0.0
    cluster: int = -1
    label: str = "ambiguous"
    confidence: float = 0.0
    score_mov: float = 0.0
    score_tiktok: float = 0.0
    score_tiktok_extended: float = 0.0
    score_ryan_tiktok: float = 0.0
    score_ryan_confirmed: float = 0.0
    score_rejected_non_gage: float = 0.0


def ffmpeg_audio_only(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:a:0",
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target),
        ],
        check=True,
    )


def load_mono(path: Path, sample_rate: int = 16000) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != sample_rate:
        audio = torchaudio.functional.resample(torch.from_numpy(audio), sr, sample_rate).numpy()
    return audio


def normalized_embedding(model: EncoderClassifier, audio: np.ndarray) -> np.ndarray:
    if len(audio) < 16000:
        audio = np.pad(audio, (0, 16000 - len(audio)))
    with torch.inference_mode():
        emb = model.encode_batch(torch.from_numpy(audio).unsqueeze(0)).squeeze().cpu().numpy()
    return emb / max(float(np.linalg.norm(emb)), 1e-9)


def reference_embedding(model: EncoderClassifier, path: Path) -> tuple[np.ndarray, list[np.ndarray]]:
    audio = load_mono(path)
    window = 3 * 16000
    hop = 2 * 16000
    pieces = []
    for start in range(0, max(1, len(audio) - 16000 + 1), hop):
        part = audio[start:min(start + window, len(audio))]
        if len(part) >= 16000:
            pieces.append(normalized_embedding(model, part))
    centroid = np.mean(pieces, axis=0)
    centroid /= np.linalg.norm(centroid)
    return centroid, pieces


def make_chunks(result: dict, source: Path, audio: np.ndarray, model: EncoderClassifier) -> list[Chunk]:
    chunks: list[Chunk] = []
    for segment in result["segments"]:
        words = [w for w in segment.get("words", []) if w.get("word", "").strip()]
        groups: list[list[dict]] = []
        current: list[dict] = []
        for word in words:
            current.append(word)
            duration = float(current[-1]["end"]) - float(current[0]["start"])
            if duration >= 4.5:
                groups.append(current)
                current = []
        if current:
            if groups and float(current[-1]["end"]) - float(current[0]["start"]) < 1.0:
                groups[-1].extend(current)
            else:
                groups.append(current)
        if not groups:
            groups = [[{"start": segment["start"], "end": segment["end"], "word": segment["text"]}]]

        for group in groups:
            start = max(0.0, float(group[0]["start"]) - 0.05)
            end = min(len(audio) / 16000, float(group[-1]["end"]) + 0.05)
            if end - start < 0.8:
                continue
            samples = audio[int(start * 16000):int(end * 16000)]
            rms = math.sqrt(float(np.mean(np.square(samples))) + 1e-12)
            rms_db = 20 * math.log10(rms + 1e-12)
            if rms_db < -48:
                continue
            chunks.append(
                Chunk(
                    source=source,
                    start=start,
                    end=end,
                    text="".join(str(w["word"]) for w in group).strip(),
                    embedding=normalized_embedding(model, samples),
                    rms_db=rms_db,
                )
            )
    return chunks


def write_clip(chunk: Chunk, wav_source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-ss", f"{chunk.start:.3f}",
            "-to", f"{chunk.end:.3f}", "-i", str(wav_source), "-ac", "1", "-ar", "24000",
            "-c:a", "pcm_s16le", str(destination),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("input/candidates/audio_only"))
    parser.add_argument("--work", type=Path, default=Path(".speaker_analysis"))
    parser.add_argument("--whisper-model", default="small.en")
    parser.add_argument(
        "--source-glob", default="Hidden - * of 6.m4a",
        help="Input filename glob. WAV inputs are analyzed directly without remixing.",
    )
    parser.add_argument(
        "--result-name", default="results_v5",
        help="Result directory name beneath --work.",
    )
    args = parser.parse_args()

    work = args.work.resolve()
    wav_dir = work / "wav"
    result_dir = work / args.result_name
    result_dir.mkdir(parents=True, exist_ok=True)

    local_speaker_model = work / "models" / "spkrec-ecapa-voxceleb"
    model = EncoderClassifier.from_hparams(
        source=str(local_speaker_model),
        savedir=str(local_speaker_model),
        run_opts={"device": "cpu"},
    )
    whisper_model = whisper.load_model(args.whisper_model, device="cpu")

    references = [
        Path("voices/on_camera_mov.wav").resolve(),
        Path("voices/archive/on_camera_tiktok_7553986048305401143.wav").resolve(),
        Path("voices/archive/gage_tiktok_extended_enrollment.wav").resolve(),
    ]
    ref_centroids = []
    ref_pieces = []
    for ref in references:
        centroid, pieces = reference_embedding(model, ref)
        ref_centroids.append(centroid)
        ref_pieces.extend(pieces)
    # Equal weight per source so the longer extended TikTok enrollment does not
    # overwhelm the independent MOV reference.
    gage_centroid = np.mean(ref_centroids, axis=0)
    gage_centroid /= np.linalg.norm(gage_centroid)
    cross_reference_similarity = float(np.dot(ref_centroids[0], ref_centroids[1]))
    ryan_references = [
        Path("voices/archive/ryan_tiktok_7553986048305401143.wav").resolve(),
        Path(
            ".speaker_analysis/final/accepted/ryan/"
            "Hidden - 6 of 6_00531.950_00533.570.wav"
        ).resolve(),
    ]
    ryan_centroids = [reference_embedding(model, ref)[0] for ref in ryan_references]
    ryan_centroid = np.mean(ryan_centroids, axis=0)
    ryan_centroid /= np.linalg.norm(ryan_centroid)
    gage_ryan_similarity = float(np.dot(gage_centroid, ryan_centroid))
    rejected_non_gage = [
        Path(
            ".speaker_analysis/final/quarantine/rejected_by_user/"
            "Hidden - 2 of 6_00796.810_00798.570.wav"
        ).resolve(),
        Path(
            ".speaker_analysis/final/quarantine/rejected_by_user/"
            "Hidden - 3 of 6_00374.550_00375.830.wav"
        ).resolve(),
    ]
    rejected_centroids = [reference_embedding(model, ref)[0] for ref in rejected_non_gage]
    rejected_centroid = np.mean(rejected_centroids, axis=0)
    rejected_centroid /= np.linalg.norm(rejected_centroid)

    sources = sorted(args.input.glob(args.source_glob))
    if not sources:
        raise SystemExit(
            f"No candidates matching {args.source_glob!r} found in {args.input}"
        )

    all_chunks: list[Chunk] = []
    wav_by_source: dict[Path, Path] = {}
    for source in sources:
        print(f"Processing audio only: {source.name}", flush=True)
        if source.suffix.lower() == ".wav":
            # Channel-recovery WAVs have already been decoded from the original
            # audio stream. Do not collapse or otherwise remix them here.
            wav = source.resolve()
        else:
            wav = wav_dir / f"{source.stem}.wav"
            ffmpeg_audio_only(source, wav)
        wav_by_source[source.resolve()] = wav
        audio = load_mono(wav)
        transcript_path = result_dir / f"{source.stem}.transcript.json"
        if transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        else:
            prior_transcripts = [
                work / "results_v4" / f"{source.stem}.transcript.json",
                work / "results_v3" / f"{source.stem}.transcript.json",
                work / "results_v2" / f"{source.stem}.transcript.json",
                work / "results" / f"{source.stem}.transcript.json",
                work / "quarantine" / "obsolete_runs" / "forced_two_cluster_results" /
                    f"{source.stem}.transcript.json",
            ]
            prior_transcript = next((p for p in prior_transcripts if p.exists()), None)
            if prior_transcript is not None:
                transcript = json.loads(prior_transcript.read_text(encoding="utf-8"))
            else:
                transcript = whisper_model.transcribe(
                    str(wav), language="en", fp16=False, word_timestamps=True,
                    condition_on_previous_text=False, verbose=False,
                )
            transcript_path.write_text(
                json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        all_chunks.extend(make_chunks(transcript, source.resolve(), audio, model))

    embeddings = np.stack([c.embedding for c in all_chunks])
    raw_gage_scores = embeddings @ gage_centroid
    farthest = embeddings[int(np.argmin(raw_gage_scores))]
    clustering = KMeans(
        n_clusters=2, init=np.stack([gage_centroid, farthest]), n_init=1, random_state=42
    ).fit(embeddings)
    centers = clustering.cluster_centers_
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    gage_cluster = int(np.argmax(centers @ gage_centroid))
    ryan_cluster = 1 - gage_cluster

    # Require independent agreement with both enrollment recordings. The long
    # candidates contain background media, so a two-cluster assignment alone
    # cannot safely distinguish Ryan from other voices.
    for chunk, cluster in zip(all_chunks, clustering.labels_):
        scores = centers @ chunk.embedding
        margin = float(scores[gage_cluster] - scores[ryan_cluster])
        chunk.score_mov = float(np.dot(chunk.embedding, ref_centroids[0]))
        chunk.score_tiktok = float(np.dot(chunk.embedding, ref_centroids[1]))
        chunk.score_tiktok_extended = float(np.dot(chunk.embedding, ref_centroids[2]))
        chunk.score_gage = float(np.dot(chunk.embedding, gage_centroid))
        score_ryan = float(np.dot(chunk.embedding, ryan_centroid))
        chunk.score_ryan_tiktok = float(np.dot(chunk.embedding, ryan_centroids[0]))
        chunk.score_ryan_confirmed = float(np.dot(chunk.embedding, ryan_centroids[1]))
        chunk.score_rejected_non_gage = float(np.dot(chunk.embedding, rejected_centroid))
        chunk.cluster = int(cluster)
        chunk.confidence = abs(margin)
        tiktok_score = max(chunk.score_tiktok, chunk.score_tiktok_extended)
        dual_mean = (chunk.score_mov + tiktok_score) / 2
        blocked_text = any(term in chunk.text.lower() for term in (
            "performing", "platinum album", "cover", "song's", "my mind, my mind",
            "waiting so long", "love like this",
        ))
        ryan_score = max(chunk.score_ryan_tiktok, chunk.score_ryan_confirmed)
        if (
            chunk.end - chunk.start >= 1.2
            and len(chunk.text.split()) >= 2
            and not blocked_text
            and max(chunk.score_mov, tiktok_score) >= 0.20
            and dual_mean >= 0.13
            and dual_mean - ryan_score >= 0.07
            and dual_mean - chunk.score_rejected_non_gage >= 0.03
        ):
            chunk.label = "gage_review"
        elif (
            chunk.end - chunk.start >= 1.2
            and len(chunk.text.split()) >= 2
            and ryan_score >= 0.25
            and ryan_score - dual_mean >= 0.08
        ):
            chunk.label = "ryan_review"
        else:
            chunk.label = "bad_data"
        chunk.confidence = abs(dual_mean - score_ryan)
        # Stored dynamically to keep the dataclass focused on selection state.
        chunk.score_ryan = score_ryan

    manifest = result_dir / "speaker_manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as handle:
        for index, chunk in enumerate(all_chunks):
            clip_name = f"{chunk.source.stem}_{chunk.start:09.3f}_{chunk.end:09.3f}.wav"
            if chunk.label == "gage_review":
                clip_path = result_dir / "review" / "gage" / clip_name
            elif chunk.label == "ryan_review":
                clip_path = result_dir / "review" / "ryan" / clip_name
            else:
                clip_path = result_dir / "quarantine" / "bad_data" / clip_name
            write_clip(chunk, wav_by_source[chunk.source], clip_path)
            handle.write(json.dumps({
                "source": str(chunk.source), "start": round(chunk.start, 3),
                "end": round(chunk.end, 3), "duration": round(chunk.end - chunk.start, 3),
                "text_draft": chunk.text, "label": chunk.label,
                "gage_similarity": round(chunk.score_gage, 5),
                "mov_similarity": round(chunk.score_mov, 5),
                "tiktok_similarity": round(chunk.score_tiktok, 5),
                "tiktok_extended_similarity": round(chunk.score_tiktok_extended, 5),
                "ryan_similarity": round(chunk.score_ryan, 5),
                "ryan_tiktok_similarity": round(chunk.score_ryan_tiktok, 5),
                "ryan_confirmed_similarity": round(chunk.score_ryan_confirmed, 5),
                "rejected_non_gage_similarity": round(chunk.score_rejected_non_gage, 5),
                "cluster_margin": round(chunk.confidence, 5),
                "rms_db": round(chunk.rms_db, 2), "clip": str(clip_path),
            }, ensure_ascii=False) + "\n")

    counts = {label: sum(c.label == label for c in all_chunks)
              for label in ("gage_review", "ryan_review", "bad_data")}
    durations = {label: round(sum(c.end - c.start for c in all_chunks if c.label == label), 2)
                 for label in counts}
    summary = {
        "cross_reference_similarity": round(cross_reference_similarity, 5),
        "gage_ryan_reference_similarity": round(gage_ryan_similarity, 5),
        "gage_cluster": gage_cluster,
        "cluster_similarity_to_gage": [round(float(x), 5) for x in centers @ gage_centroid],
        "counts": counts,
        "durations_seconds": durations,
        "warning": "Machine labels are candidates only; approve by listening before training.",
    }
    (result_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(manifest)


if __name__ == "__main__":
    main()
