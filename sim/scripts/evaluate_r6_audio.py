"""Replay audio through the frozen R6 classifier using one-second segments."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(__file__).resolve().parents[2] / "sim/work/numba_cache"))
sys.dont_write_bytecode = True

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SR = 16000

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, records):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def load_inputs():
    manifest_path = ROOT / "data/classification_r6/input_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))["files"]


class PowerProvider:
    def receive_batch(self):
        return self.batch


def vote(labels):
    counts = collections.Counter(label for label in labels if label != "silence")
    if not counts:
        return "silence", {}, False
    maximum = max(counts.values())
    winners = [label for label, count in counts.items() if count == maximum]
    return (winners[0] if len(winners) == 1 else "tie"), dict(counts), len(winners) > 1


def read_audio(path):
    data, source_rate = sf.read(path, dtype="float32", always_2d=True)
    channels = data.shape[1]
    mono = np.mean(data, axis=1, dtype=np.float32)
    if source_rate != SR:
        import librosa
        mono = librosa.resample(mono, orig_sr=source_rate, target_sr=SR,
                               res_type="soxr_hq", fix=True, scale=False)
    if not len(mono) or not np.isfinite(mono).all():
        raise ValueError("Audio must contain finite samples")
    return mono, int(source_rate), int(channels)


def make_power(segment):
    padded = np.pad(np.asarray(segment, dtype="float32"), (512, 512), mode="constant")
    frames = np.lib.stride_tricks.sliding_window_view(padded, 1024)[::256]
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(1024) / 1024)
    return (np.abs(np.fft.rfft(frames * window, axis=1)) ** 2).T


def summarize(records):
    groups = collections.defaultdict(list)
    for record in records:
        groups[record["suite"]].append(record)
    summaries = []
    for suite, files in groups.items():
        summaries.append({
            "suite": suite,
            "files": len(files),
            "first_second_correct": sum(row["first_second_correct"] for row in files),
            "cnn_file_vote_correct": sum(row["cnn_file_correct"] for row in files),
            "r6_file_vote_correct": sum(row["r6_file_correct"] for row in files),
            "r6_file_accuracy": sum(row["r6_file_correct"] for row in files) / len(files),
            "segments": sum(row["segments"] for row in files),
            "active_segments": sum(row["active_segments"] for row in files),
            "matching_active_segments": sum(row["matching_active_segments"] for row in files),
            "duplicate_files": sum(bool(row["byte_identical_to"]) for row in files),
        })
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "sim/results/r6_replay01")
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Use a NEW --out directory")
    started = time.perf_counter()
    expected = load_inputs()
    output = args.out.resolve()
    output.mkdir(parents=True)
    runtime = ROOT / "board/runtime"
    sys.path.insert(0, str(runtime))
    from run_live_system import verify_bit_pair
    from reference_infer import ReferenceSession
    from model_stream import AudioPianoReferenceModel, apply_piano_support, review_instrument
    from pl_fft import power_to_mel
    from infer_numpy import mel_spectrogram_np

    release = verify_bit_pair(runtime / "audio_merged.bit")
    provider = PowerProvider()
    session = ReferenceSession(provider, runtime / "models", runtime / "reference")
    wrapped = AudioPianoReferenceModel(session.model, runtime / "reference")
    session.model = session.base.model = wrapped
    snapshot = {
        "date": "2026-11-04",
        "evaluation": "PC audio replay through frozen R6 runtime classification",
        "software_release": release["software_release"],
        "weights_sha256": digest(runtime / "models/cnn_weights.npz"),
        "piano_support": True,
        "piano_review": False,
        "sample_rate": SR,
        "segment_samples": SR,
        "segment_hop_samples": SR,
        "final_partial_segment": "zero_pad_to_one_second",
        "file_aggregation": "majority_of_non_silent_segments_ties_remain_tie",
        "pcm_frontend": "soundfile_float32_arithmetic_channel_mean_soxr_hq_to_16k_no_gain_normalization",
        "spectrum": "float64_numpy_rfft_periodic_hann1024_hop256_center_zero_pad_63frames",
        "hardware_fft_quantization_simulated": False,
        "physical_board_execution": False,
        "label_source": "provided_manifest_labels_not_independently_audited",
        "timings": "host_compute_only",
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ("numpy", "soundfile", "librosa", "soxr")},
        "runtime_hashes": {name: digest(runtime / name) for name in (
            "infer_numpy.py", "pl_fft.py", "reference_infer.py", "model_stream.py",
            "models/cnn_weights.npz", "models/mel_matrix.npy", "reference/reference_bank.npz")},
    }
    (output / "run_manifest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    files = []
    segments = []
    cache = {}
    with (output / "segment_results.jsonl").open("w", encoding="utf-8") as stream:
        for index, item in enumerate(expected, 1):
            path = ROOT / item["audio_file"]
            if digest(path) != item["sha256"]:
                raise ValueError("Input hash mismatch: " + item["file_id"])
            if item["sha256"] in cache:
                record, saved = cache[item["sha256"]]
                record = dict(record, **item)
                per_file = [dict(row, file_id=item["file_id"], suite=item["suite"]) for row in saved]
            else:
                audio, source_rate, channels = read_audio(path)
                per_file = []
                session.base.previous_segment = None
                for sequence, start in enumerate(range(0, len(audio), SR)):
                    part = audio[start:start + SR]
                    real_samples = len(part)
                    part = np.pad(part, (0, SR - real_samples))
                    power = make_power(part)
                    if sequence == 0:
                        np.testing.assert_allclose(power_to_mel(power, session.matrix),
                                                   mel_spectrogram_np(part, session.matrix), atol=1e-6)
                    provider.batch = dict(power=power, segment=sequence, start=start, dropped=0,
                                          exponents=np.zeros(63, dtype="u1"))
                    result = review_instrument(apply_piano_support(session.next(), enabled=True), enabled=False)
                    probabilities = result.get("cnn_probabilities") or {}
                    support = result.get("piano_support") or {}
                    row = {
                        "file_id": item["file_id"], "suite": item["suite"],
                        "reference_label": item["reference_label"], "segment": sequence,
                        "start_s": start / SR, "source_end_s": (start + real_samples) / SR,
                        "padded_samples": SR - real_samples, "rms_est": result["rms_est"],
                        "cnn_label": result["cnn_label"], "r6_label": result["label"],
                        "cnn_confidence": result["cnn_confidence"],
                        "r6_confidence": result["confidence"],
                        "decision_source": result.get("decision_source", "cnn"),
                        "piano_support_applied": bool(support.get("applied")),
                        "prob_piano": probabilities.get("piano"),
                        "prob_guitar": probabilities.get("guitar"),
                        "prob_violin": probabilities.get("violin"),
                        "host_compute_ms": result["compute_ms"],
                    }
                    per_file.append(row)
                raw, raw_votes, raw_tie = vote(row["cnn_label"] for row in per_file)
                final, final_votes, final_tie = vote(row["r6_label"] for row in per_file)
                active = [row for row in per_file if row["r6_label"] != "silence"]
                record = dict(item, duration_s=len(audio) / SR, source_sample_rate=source_rate,
                              source_channels=channels, segments=len(per_file), active_segments=len(active),
                              silence_segments=len(per_file) - len(active),
                              first_second_prediction=per_file[0]["r6_label"],
                              first_second_correct=int(per_file[0]["r6_label"] == item["reference_label"]),
                              cnn_file_prediction=raw, cnn_file_correct=int(raw == item["reference_label"]),
                              r6_file_prediction=final, r6_file_correct=int(final == item["reference_label"]),
                              matching_active_segments=sum(row["r6_label"] == item["reference_label"] for row in active),
                              piano_support_changes=sum(row["piano_support_applied"] for row in per_file),
                              cnn_votes=json.dumps(raw_votes, sort_keys=True),
                              r6_votes=json.dumps(final_votes, sort_keys=True), file_vote_tied=final_tie,
                              error="")
                cache[item["sha256"]] = (record, per_file)
            for row in per_file:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            segments.extend(per_file)
            files.append(record)
            print(f"[{index}/{len(expected)}] {item['suite']} {Path(item['audio_file']).name} "
                  f"truth={item['reference_label']} predicted={record['r6_file_prediction']} "
                  f"active={record['active_segments']}/{record['segments']}", flush=True)
    summaries = summarize(files)
    unique = [row for row in files if not row["byte_identical_to"]]
    summary = dict(snapshot, files=len(files), byte_unique_files=len(unique),
                   file_vote_correct=sum(row["r6_file_correct"] for row in files),
                   byte_unique_vote_correct=sum(row["r6_file_correct"] for row in unique),
                   segments=len(segments), elapsed_s=time.perf_counter() - started, suites=summaries)
    write_csv(output / "file_results.csv", files)
    write_csv(output / "segment_results.csv", segments)
    write_csv(output / "suite_summary.csv", summaries)
    write_csv(output / "failed_files.csv", [row for row in files if not row["r6_file_correct"]])
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EVALUATION_COMPLETE", json.dumps({k: summary[k] for k in (
        "files", "byte_unique_files", "file_vote_correct", "byte_unique_vote_correct", "segments", "elapsed_s")}), flush=True)


if __name__ == "__main__":
    main()
