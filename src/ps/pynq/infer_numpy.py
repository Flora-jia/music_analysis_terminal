# -*- coding: utf-8 -*-
"""
纯 numpy 版乐器识别推理（PC / PYNQ 板通用，不需要 tflite_runtime / tensorflow）

背景：Zynq-7020 的 Cortex-A9 只支持 VFPv3 浮点，而 Coral 的 tflite_runtime wheel
      按 VFPv4 编译 → 板上 invoke() 报 "Illegal instruction (core dumped)"。
      本模块用 numpy 重写这个 4 层小 CNN，彻底绕开二进制兼容问题。

用法：
    from infer_numpy import NumpyInstrumentClassifier, mel_spectrogram_np
    clf = NumpyInstrumentClassifier("cnn_weights.npz", "model_meta.json")
    mel = mel_spectrogram_np(y_16k_1s)          # (64, 63)
    idx, name, conf = clf.infer_stable(mel)

依赖：仅 numpy（板上已有）
"""
import json

import numpy as np

# 特征参数——必须与训练一致（队友口径）
SR, N_FFT, HOP, N_MELS, FMAX, FRAMES = 16000, 1024, 256, 64, 8000, 63
_WIN = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)   # periodic hann


def mel_spectrogram_np(y, mel_matrix):
    """1D 音频 -> (64,63) log-mel，与 librosa.feature.melspectrogram(power=2)+power_to_db 对齐。
    mel_matrix: (64,513)（librosa.filters.mel 生成的梅尔滤波矩阵）"""
    y = np.pad(np.asarray(y, dtype=np.float32), N_FFT // 2, mode="constant")
    n_fr = 1 + (len(y) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_fr)[:, None]
    frames = y[idx] * _WIN
    spec = np.fft.rfft(frames, n=N_FFT, axis=1)
    mel = mel_matrix @ (np.abs(spec) ** 2).T
    db = 10.0 * np.log10(np.maximum(1e-10, mel))
    db -= db.max()
    m = np.clip((db + 80.0) / 80.0, 0.0, 1.0)
    if m.shape[1] < FRAMES:
        m = np.pad(m, ((0, 0), (0, FRAMES - m.shape[1])))
    return m[:, :FRAMES].astype(np.float32)


def _conv_same_relu(x, w, b):
    H, W, _ = x.shape
    kh, kw, _, cout = w.shape
    xp = np.pad(x, ((kh // 2, kh // 2), (kw // 2, kw // 2), (0, 0)))
    out = np.zeros((H, W, cout), np.float32)
    for i in range(kh):
        for j in range(kw):
            out += xp[i:i + H, j:j + W, :] @ w[i, j]
    out += b
    return np.maximum(out, 0)


def _maxpool2(x):
    H, W, C = x.shape
    h2, w2 = H // 2, W // 2
    return x[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2, C).max(axis=(1, 3))


class NumpyInstrumentClassifier:
    def __init__(self, weights_path, meta_path):
        z = np.load(weights_path)
        self.w = {k: z[k] for k in z.files}
        with open(meta_path, encoding="utf-8") as f:
            self.labels = json.load(f)["labels"]
        self._prob_hist = []
        self._stable_idx = None

    def infer(self, mel):
        """mel: (64,63) -> (label_idx, probs[3])"""
        x = mel[..., None].astype(np.float32)
        x = _maxpool2(_conv_same_relu(x, self.w["conv2d_w"], self.w["conv2d_b"]))
        x = _maxpool2(_conv_same_relu(x, self.w["conv2d_1_w"], self.w["conv2d_1_b"]))
        x = _maxpool2(_conv_same_relu(x, self.w["conv2d_2_w"], self.w["conv2d_2_b"]))
        x = x.mean(axis=(0, 1))                       # GlobalAveragePooling
        y = x @ self.w["dense_w"] + self.w["dense_b"]
        e = np.exp(y - y.max())
        probs = (e / e.sum()).astype(np.float32)
        return int(probs.argmax()), probs

    def infer_stable(self, mel, hist_len=3, switch_margin=0.15):
        """滑动窗口投票防抖（与 tflite 版行为一致）"""
        idx, probs = self.infer(mel)
        self._prob_hist.append(probs)
        self._prob_hist = self._prob_hist[-hist_len:]
        avg = np.mean(self._prob_hist, axis=0)
        win_idx = int(np.argmax(avg))
        if self._stable_idx is None:
            self._stable_idx = win_idx
        elif win_idx != self._stable_idx and avg[win_idx] > avg[self._stable_idx] + switch_margin:
            self._stable_idx = win_idx
        return self._stable_idx, self.labels[self._stable_idx], float(avg[self._stable_idx])
