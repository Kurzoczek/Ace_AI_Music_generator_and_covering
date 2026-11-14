# -*- coding: utf-8 -*-
"""Minimal replacement for the 'soundfile' package (libsndfile is not available inside the Android app).

Supports WAV files only: reading PCM 8/16/24/32-bit and IEEE float 32/64-bit (also WAVE_FORMAT_EXTENSIBLE),
writing PCM_16, PCM_24, PCM_32 and FLOAT. The app decodes every input format (MP3, AAC, FLAC, OGG...) to WAV
with Android MediaCodec before Python sees it, and acestep.cpp writes WAV as well.
"""
import struct

import numpy as np

_PCM, _FLOAT, _EXTENSIBLE = 1, 3, 0xFFFE


def _chunks(f):
    while True:
        head = f.read(8)
        if len(head) < 8:
            return
        cid, size = head[:4], struct.unpack("<I", head[4:])[0]
        yield cid, size
        # caller reads or skips; chunks are word aligned


def info(path):
    with open(path, "rb") as f:
        return _parse_header(f)[0]


def _parse_header(f):
    riff = f.read(12)
    if len(riff) < 12 or riff[:4] not in (b"RIFF", b"RF64") or riff[8:12] != b"WAVE":
        raise ValueError(f"not a WAV file: {getattr(f, 'name', '?')}")
    fmt = None
    data_size_64 = None
    for cid, size in _chunks(f):
        if cid == b"ds64":
            body = f.read(size)
            data_size_64 = struct.unpack("<Q", body[8:16])[0]
        elif cid == b"fmt ":
            body = f.read(size)
            tag, ch, sr, _, block, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == _EXTENSIBLE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = {"format": tag, "channels": ch, "samplerate": sr, "block": block, "bits": bits}
        elif cid == b"data":
            if fmt is None:
                raise ValueError("WAV without a fmt chunk before data")
            if size == 0xFFFFFFFF and data_size_64 is not None:
                size = data_size_64
            fmt["frames"] = size // fmt["block"]
            return fmt, size
        else:
            f.seek(size + (size & 1), 1)
        if size & 1 and cid in (b"fmt ", b"ds64"):
            f.seek(1, 1)
    raise ValueError("WAV without a data chunk")


def read(path, dtype="float32", always_2d=False, start=0, frames=-1):
    with open(path, "rb") as f:
        fmt, size = _parse_header(f)
        ch, bits, tag = fmt["channels"], fmt["bits"], fmt["format"]
        bps = bits // 8
        total = fmt["frames"]
        start = max(0, min(int(start), total))
        n = total - start if frames is None or frames < 0 else min(int(frames), total - start)
        f.seek(start * fmt["block"], 1)
        raw = f.read(n * fmt["block"])
    n = len(raw) // fmt["block"]
    raw = raw[:n * fmt["block"]]
    if tag == _FLOAT:
        x = np.frombuffer(raw, dtype="<f4" if bits == 32 else "<f8").astype(np.float32)
    elif tag == _PCM:
        if bits == 8:
            x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif bits == 16:
            x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif bits == 24:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            v = np.where(v & 0x800000, v - 0x1000000, v)
            x = v.astype(np.float32) / 8388608.0
        elif bits == 32:
            x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"unsupported PCM bit depth: {bits}")
    else:
        raise ValueError(f"unsupported WAV format tag: {tag}")
    x = x.reshape(-1, ch)
    if dtype != "float32":
        x = x.astype(dtype)
    if not always_2d and ch == 1:
        x = x[:, 0]
    return x, fmt["samplerate"]


def write(path, data, samplerate, subtype="PCM_16"):
    x = np.asarray(data, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    ch = x.shape[1]
    x = np.clip(x, -1.0, 1.0)
    subtype = (subtype or "PCM_16").upper()
    if subtype == "FLOAT":
        tag, bits, payload = _FLOAT, 32, x.astype("<f4").tobytes()
    elif subtype == "PCM_32":
        tag, bits, payload = _PCM, 32, (x * 2147483647.0).astype("<i4").tobytes()
    elif subtype == "PCM_24":
        v = np.round(x * 8388607.0).astype("<i4").reshape(-1)
        b = v.view(np.uint8).reshape(-1, 4)[:, :3]
        tag, bits, payload = _PCM, 24, np.ascontiguousarray(b).tobytes()
    else:
        tag, bits, payload = _PCM, 16, np.round(x * 32767.0).astype("<i2").tobytes()
    block = ch * bits // 8
    sr = int(samplerate)
    fmt = struct.pack("<HHIIHH", tag, ch, sr, sr * block, block, bits)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(payload) + (len(payload) & 1)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(payload)) + payload)
        if len(payload) & 1:
            f.write(b"\x00")
