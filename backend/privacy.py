"""Privacy filters that run before anything is stored or sent to the model.

Photos: phone photos carry hidden EXIF metadata, often including the GPS spot where the photo
was taken. We re-encode every image without metadata and blur faces we can detect.

Videos: the model never sees the video file. We pull a few distinct keyframes, blur faces in
them, and send only those frames. The original video stays encrypted and visible only to its owner.

Text: before lease, bill, or letter text goes to the model, emails, phone numbers, long account
numbers, street addresses, and the names we know about are replaced by placeholders such as
[PERSON_1]. The real values are put back only on this server, when a letter is shown to its owner.
"""

from __future__ import annotations

import io
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from config import IMAGE_MAX_SIDE, MAX_FRAMES_PER_VIDEO, MAX_VIDEO_SECONDS

_FACE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _blur_faces(bgr: np.ndarray) -> tuple[np.ndarray, int]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    side = min(gray.shape[:2])
    faces = _FACE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(max(40, side // 12),) * 2)
    for (x, y, w, h) in faces:
        roi = bgr[y:y + h, x:x + w]
        k = max(31, (w // 3) | 1)
        bgr[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (k, k), 0)
    return bgr, len(faces)


def _had_gps(img: Image.Image) -> bool:
    try:
        exif = img.getexif()
        return bool(exif.get_ifd(0x8825))  # GPS IFD
    except Exception:
        return False


def sanitize_image(data: bytes, max_side: int = 2048) -> tuple[bytes, dict]:
    """Return a clean JPEG (no EXIF, upright, faces blurred) and what was removed."""
    img = Image.open(io.BytesIO(data))
    had_exif = bool(img.info.get("exif")) or bool(getattr(img, "getexif", lambda: {})())
    had_gps = _had_gps(img)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    bgr, faces = _blur_faces(bgr)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Could not encode image.")
    return buf.tobytes(), {"exif_removed": had_exif, "gps_removed": had_gps, "faces_blurred": faces,
                           "width": bgr.shape[1], "height": bgr.shape[0]}


def model_view(jpeg: bytes, max_side: int = IMAGE_MAX_SIDE) -> bytes:
    """Smaller copy for the model (fewer image tokens)."""
    arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    h, w = arr.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------

@dataclass
class Keyframe:
    t_seconds: float
    jpeg: bytes
    faces_blurred: int


def video_keyframes(data: bytes, max_frames: int = MAX_FRAMES_PER_VIDEO) -> tuple[list[Keyframe], dict]:
    """Pick distinct frames: sample every 0.5 s, keep a frame when the picture changed enough."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total / fps if fps else 0
        if duration > MAX_VIDEO_SECONDS:
            raise ValueError(f"Video is {duration:.0f}s; the limit is {MAX_VIDEO_SECONDS}s.")
        candidates: list[tuple[float, np.ndarray, np.ndarray]] = []
        step = max(1, int(fps * 0.5))
        for idx in range(0, max(total, 1), step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            small = cv2.resize(frame, (64, 64))
            hist = cv2.calcHist([cv2.cvtColor(small, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            candidates.append((idx / fps, frame, hist))
        cap.release()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    kept: list[tuple[float, np.ndarray, np.ndarray]] = []
    for t, frame, hist in candidates:
        if not kept or cv2.compareHist(kept[-1][2], hist, cv2.HISTCMP_CORREL) < 0.90:
            kept.append((t, frame, hist))
    if candidates and kept[-1][0] != candidates[-1][0]:
        kept.append(candidates[-1])  # the end of a walkthrough usually shows the subject up close
    if len(kept) > max_frames:  # spread the picks evenly over the walkthrough
        idxs = np.linspace(0, len(kept) - 1, max_frames).round().astype(int)
        kept = [kept[i] for i in sorted(set(idxs))]

    frames: list[Keyframe] = []
    faces_total = 0
    for t, frame, _ in kept:
        h, w = frame.shape[:2]
        scale = 1280 / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        frame, faces = _blur_faces(frame)
        faces_total += faces
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frames.append(Keyframe(round(t, 1), buf.tobytes(), faces))
    meta = {"duration_s": round(duration, 1), "fps": round(fps, 1), "sampled": len(candidates),
            "keyframes": len(frames), "faces_blurred": faces_total}
    return frames, meta


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),  # no trailing sentence period
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    ("SSN", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    # not part of a longer code such as a document ID "ECR-2026-0710-4B"
    ("ACCOUNT", re.compile(r"(?<![\w$.,-])\d(?:[\d -]{6,}\d)(?![\w-])(?![.,]\d)")),
    ("ADDRESS", re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][a-z]+\.?\s){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|"
        r"Court|Ct|Place|Pl|Way|Square|Sq)\b\.?(?:\s*(?:#|Unit|Apt\.?|Apartment)\s*[\w-]+)?", re.I)),
]


@dataclass
class Masked:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> real value
    counts: dict[str, int] = field(default_factory=dict)


def mask_text(text: str, names: list[str] | tuple[str, ...] = ()) -> Masked:
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counts: dict[str, int] = {}

    def placeholder(kind: str, value: str) -> str:
        key = value.strip()
        if key in reverse:
            return reverse[key]
        counts[kind] = counts.get(kind, 0) + 1
        ph = f"[{kind}_{counts[kind]}]"
        mapping[ph] = key
        reverse[key] = ph
        return ph

    out = text
    # Number names in the order given (the account holder first, so they are always [PERSON_1]),
    # then replace longest first so "Alex Kim" is not split by a shorter "Kim".
    by_lower: dict[str, str] = {}
    for n in names:
        n = (n or "").strip()
        if len(n) >= 3 and n.lower() not in by_lower:
            by_lower[n.lower()] = placeholder("PERSON", n)
    for low in sorted(by_lower, key=len, reverse=True):
        out = re.sub(re.escape(low), by_lower[low], out, flags=re.I)

    def replace(m: re.Match, kind: str) -> str:
        value = m.group(0)
        if kind == "ACCOUNT":
            digits = sum(ch.isdigit() for ch in value)
            if digits < 8 or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
                return value  # short numbers and ISO dates are not account numbers
        return placeholder(kind, value)

    for kind, pattern in _PATTERNS:
        out = pattern.sub(lambda m, k=kind: replace(m, k), out)
    return Masked(out, mapping, counts)


_LOOSE_PH = re.compile(r"\[([A-Z]+_\d+)([^\]\n]{1,40})\]")


def unmask(text: str, mapping: dict[str, str]) -> str:
    for ph, value in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(ph, value)
    # A model sometimes writes extra words inside the brackets ("[PERSON_2's office]"); restore those too.
    return _LOOSE_PH.sub(lambda m: (mapping[f"[{m.group(1)}]"] + m.group(2)) if f"[{m.group(1)}]" in mapping else m.group(0), text)


_NAME_HINTS = re.compile(
    r"(?:Resident'?s? Name|Residents?\s*\(list all residents\)|Tenant(?:\(s\))?|Owner'?s name|Landlord|Lessor|"
    r"Subtenant|Sublessor)\s*[:\-]\s*([A-Z][A-Za-z'-]+(?:[ 	]+[A-Z][A-Za-z'-]+){0,3}"
    r"(?:[ 	]*,[ 	]*[A-Z][A-Za-z'-]+(?:[ 	]+[A-Z][A-Za-z'-]+){0,3})*)")


_LABEL_WORDS = {"phone", "home", "work", "date", "email", "signature", "unit", "address", "cell"}


def guess_names(text: str) -> list[str]:
    """Names printed next to labels like "Resident's Name:" or "Owner's name:"."""
    found: list[str] = []
    for m in _NAME_HINTS.finditer(text):
        for part in m.group(1).split(","):
            words = part.split()
            while words and words[-1].lower() in _LABEL_WORDS:  # "Alex Kim Phone:" -> "Alex Kim"
                words.pop()
            part = " ".join(words)
            if 3 <= len(part) <= 60 and part.lower() not in {"none", "n/a"}:
                found.append(part)
    return found
