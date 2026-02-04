import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from dataclasses import dataclass
from typing import List

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

import gradio as gr

# =============================
# CONFIG
# =============================
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
UPLOADS = DATA_DIR / "uploads"
OUTPUTS = DATA_DIR / "outputs"
JOBS = DATA_DIR / "jobs"

# Output folder can be a NAS mount (e.g., /mnt/nas/conversions)
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", OUTPUTS))

# Keep some free disk space to avoid filling the device
SAFETY_MARGIN = 4 * 1024**3  # 4 GB

# Conservative estimate: output + temp files can be larger than input
OUTPUT_MULTIPLIER = 2.0

for d in (UPLOADS, OUTPUTS, JOBS):
    d.mkdir(parents=True, exist_ok=True)

# Enable HEIC / HEIF support for Pillow
register_heif_opener()

# =============================
# UTILS
# =============================
def run(cmd: list[str]) -> str:
    """Run a command and return combined stdout/stderr. Raise on non-zero exit."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout.strip())
    return p.stdout or ""

def free_space(path: Path) -> int:
    """Free disk space in bytes for the filesystem containing 'path'."""
    return shutil.disk_usage(path).free

def safe_name(p: Path) -> str:
    """Sanitize a filename stem to avoid weird characters."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in p.stem)

def ext(p: Path) -> str:
    """Lowercase extension without the dot."""
    return p.suffix.lower().lstrip(".")

def safe_unlink(p: Path) -> bool:
    """Best-effort file delete."""
    try:
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False

def to_paths(file_obj) -> List[Path]:
    """
    Gradio can return:
      - a string path
      - an object with .name
      - a list of either of the above when file_count="multiple"
    """
    if file_obj is None:
        return []
    if isinstance(file_obj, list):
        out: List[Path] = []
        for f in file_obj:
            if isinstance(f, str):
                out.append(Path(f))
            elif hasattr(f, "name"):
                out.append(Path(f.name))
            else:
                raise RuntimeError(f"Unknown upload type: {type(f)}")
        return out
    if isinstance(file_obj, str):
        return [Path(file_obj)]
    if hasattr(file_obj, "name"):
        return [Path(file_obj.name)]
    raise RuntimeError(f"Unknown upload type: {type(file_obj)}")

def clear_output(last_output_path: str):
    """Clear only the last output file from disk and reset output UI."""
    out_val = None
    logs_val = ""

    if last_output_path:
        safe_unlink(Path(last_output_path))

    return out_val, logs_val, ""

def clear_all(last_output_path: str):
    """Delete everything inside UPLOADS and OUTPUTS, then reset the UI."""
    for p in UPLOADS.glob("**/*"):
        try:
            if p.is_file():
                p.unlink()
        except Exception:
            pass

    for p in OUTPUTS.glob("**/*"):
        try:
            if p.is_file():
                p.unlink()
        except Exception:
            pass

    # Reset UI: input, output, logs, last_output
    return None, None, "", ""

# =============================
# CONVERSION MATRIX
# =============================
# For each input extension, list allowed targets.
CONVERSION_MATRIX = {
    "jpg": {"png", "webp", "tiff", "pdf"},
    "jpeg": {"png", "webp", "tiff", "pdf"},
    "png": {"jpg", "webp", "tiff", "pdf"},
    "webp": {"png", "jpg", "tiff"},
    "tiff": {"png", "jpg", "webp"},

    # HEIC / HEIF
    "heic": {"jpg", "jpeg", "png", "webp", "tiff", "pdf"},
    "heif": {"jpg", "jpeg", "png", "webp", "tiff", "pdf"},

    "mp4": {"webm", "mp3", "wav", "mkv"},
    "mkv": {"mp4", "webm", "mp3", "wav"},
    "mp3": {"wav"},
    "wav": {"mp3"},

    "doc": {"pdf"},
    "docx": {"pdf"},
    "ppt": {"pdf"},
    "pptx": {"pdf"},
    "xls": {"pdf"},
    "xlsx": {"pdf"},
    "odt": {"pdf"},
    "ods": {"pdf"},
    "odp": {"pdf"},

    "pdf": {"ocrpdf", "png", "jpg"},
}

# =============================
# FILE TASK
# =============================
@dataclass
class FileTask:
    path: Path
    size: int
    ext: str

# =============================
# CONVERTERS
# =============================
def heic_to_image(in_path: Path, out_path: Path, target: str) -> str:
    """Convert HEIC/HEIF to common image formats (or PDF)."""
    with Image.open(in_path) as img:
        # Fix iPhone-style EXIF orientation
        img = ImageOps.exif_transpose(img)

        if img.mode != "RGB":
            img = img.convert("RGB")

        if target in {"jpg", "jpeg"}:
            img.save(out_path, "JPEG", quality=95)
        elif target == "png":
            img.save(out_path, "PNG")
        elif target == "webp":
            img.save(out_path, "WEBP", quality=95)
        elif target == "tiff":
            img.save(out_path, "TIFF")
        elif target == "pdf":
            tmp_img = out_path.with_suffix(".jpg")
            img.save(tmp_img, "JPEG", quality=95)
            run(["magick", str(tmp_img), str(out_path)])
            tmp_img.unlink()
        else:
            raise RuntimeError("Unsupported HEIC output format")

    return "HEIC conversion OK"

def convert_one(in_path: Path, out_path: Path, target: str) -> str:
    """Convert one file to the desired target format."""
    input_ext = ext(in_path)

    # HEIC / HEIF handled by Pillow
    if input_ext in {"heic", "heif"}:
        return heic_to_image(in_path, out_path, target)

    # Images via ImageMagick
    if target in {"png", "jpg", "jpeg", "webp", "tiff"}:
        return run(["magick", str(in_path), str(out_path)])

    # Audio/video via FFmpeg
    if target in {"mp4", "webm", "mp3", "wav", "mkv"}:
        return run(["ffmpeg", "-y", "-i", str(in_path), str(out_path)])

    # Office documents to PDF via LibreOffice
    if target == "pdf":
        tmp = out_path.parent / f"{out_path.stem}_lo"
        tmp.mkdir(exist_ok=True)
        logs = run([
            "soffice", "--headless", "--nologo", "--nofirststartwizard",
            "--convert-to", "pdf",
            "--outdir", str(tmp),
            str(in_path)
        ])
        produced = next(tmp.glob("*.pdf"), None)
        if not produced:
            raise RuntimeError("LibreOffice produced no output")
        shutil.move(produced, out_path)
        shutil.rmtree(tmp, ignore_errors=True)
        return logs

    # OCR on PDF via OCRmyPDF
    if target == "ocrpdf":
        return run(["ocrmypdf", "--skip-text", str(in_path), str(out_path)])

    raise RuntimeError("Missing converter for this target")

# =============================
# BATCH PLANNER
# =============================
def make_batches(files: List[FileTask]) -> List[List[FileTask]]:
    """
    Create batches that fit within available disk space (minus safety margin).
    We estimate disk usage as input_size * OUTPUT_MULTIPLIER to account for outputs/temp files.
    """
    batches: List[List[FileTask]] = []
    remaining = files[:]

    while remaining:
        usable = free_space(DATA_DIR) - SAFETY_MARGIN
        if usable <= 0:
            raise RuntimeError("Insufficient disk space (after safety margin)")

        batch: List[FileTask] = []
        used = 0

        for f in remaining:
            est = int(f.size * OUTPUT_MULTIPLIER)
            if used + est > usable:
                break
            batch.append(f)
            used += est

        if not batch:
            raise RuntimeError("A file is too large for the available disk space")

        batches.append(batch)
        remaining = remaining[len(batch):]

    return batches

# =============================
# MAIN CONVERT FUNCTION
# =============================
def convert(file_obj, target: str):
    logs: List[str] = []
    outputs: List[Path] = []

    sources = to_paths(file_obj)
    if not sources:
        return None, "❌ No files provided", ""

    # -----------------------------
    # STORAGE GUARD (Solution A)
    # If user uploads too much at once, delete uploads and ask for smaller batches.
    # -----------------------------
    total_size = 0
    existing_sources: List[Path] = []
    for p in sources:
        if p.exists() and p.is_file():
            existing_sources.append(p)
            total_size += p.stat().st_size

    available = free_space(DATA_DIR) - SAFETY_MARGIN
    if total_size > available:
        # Free space ASAP: delete uploaded files
        for p in existing_sources:
            safe_unlink(p)

        msg = (
            "❌ Upload too large: the selected files exceed the available storage on this device.\n"
            f"   - Selected: {total_size/1024**3:.2f} GB\n"
            f"   - Available (after safety margin): {max(available, 0)/1024**3:.2f} GB\n"
            "✅ Please upload fewer files (smaller batch) and try again."
        )
        return None, msg, ""

    tasks: List[FileTask] = []
    extract_dirs: List[Path] = []

    # Build tasks list from multiple sources
    for src in sources:
        if not src.exists():
            logs.append(f"❌ Missing upload (temporary file): {src}")
            continue

        if src.suffix.lower() == ".zip":
            # Optional: refuse too-large zip extraction based on uncompressed size
            try:
                with zipfile.ZipFile(src) as z:
                    uncompressed = sum(i.file_size for i in z.infolist())
                if uncompressed > (free_space(DATA_DIR) - SAFETY_MARGIN):
                    logs.append(
                        "❌ ZIP extraction too large for available storage. "
                        "Please split your ZIP into smaller parts and try again."
                    )
                    safe_unlink(src)
                    continue
            except Exception:
                # If we cannot inspect the zip safely, we proceed but still handle failures later.
                pass

            extract_dir = UPLOADS / f"zip_{uuid.uuid4().hex[:6]}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            extract_dirs.append(extract_dir)

            with zipfile.ZipFile(src) as z:
                z.extractall(extract_dir)

            for p in extract_dir.rglob("*"):
                if p.is_file():
                    tasks.append(FileTask(p, p.stat().st_size, ext(p)))

            # Delete the uploaded ZIP itself to free space ASAP
            safe_unlink(src)

        else:
            tasks.append(FileTask(src, src.stat().st_size, ext(src)))

    # Filter non-convertible (delete immediately, but do not block others)
    valid: List[FileTask] = []
    for t in tasks:
        if t.ext not in CONVERSION_MATRIX or target not in CONVERSION_MATRIX[t.ext]:
            logs.append(f"❌ Skipped (not compatible): {t.path.name}")
            safe_unlink(t.path)
        else:
            valid.append(t)

    if not valid:
        for d in extract_dirs:
            shutil.rmtree(d, ignore_errors=True)
        return None, "\n".join(logs), ""

    # Batch plan
    try:
        batches = make_batches(valid)
    except Exception as e:
        for d in extract_dirs:
            shutil.rmtree(d, ignore_errors=True)
        return None, f"❌ {e}", ""

    # Process batches
    for batch in batches:
        for f in batch:
            job = uuid.uuid4().hex[:8]
            in_path = UPLOADS / f"{safe_name(f.path)}_{job}.{f.ext}"

            # Copy into our working area then delete the original ASAP
            shutil.copy(f.path, in_path)
            safe_unlink(f.path)

            out_ext = "pdf" if target == "ocrpdf" else target
            out_path = OUTPUT_ROOT / f"{safe_name(f.path)}_{job}.{out_ext}"

            try:
                logs.append(f"▶ Processing: {f.path.name}")
                logs.append(convert_one(in_path, out_path, target))
                outputs.append(out_path)
            except Exception as e:
                logs.append(f"❌ Error {f.path.name}: {e}")
            finally:
                safe_unlink(in_path)

    # Zip outputs if multiple
    if len(outputs) == 1:
        result = outputs[0]
    else:
        zip_out = OUTPUT_ROOT / f"results_{uuid.uuid4().hex[:6]}.zip"
        with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as z:
            for o in outputs:
                z.write(o, o.name)
                safe_unlink(o)
        result = zip_out

    # Cleanup extracted dirs
    for d in extract_dirs:
        shutil.rmtree(d, ignore_errors=True)

    return str(result), "\n".join(logs), str(result)

# =============================
# UI
# =============================
CSS = """
.gradio-container { max-width: 1200px !important; }
.frame { padding: 12px !important; background: #fff; min-height: 260px; }
.center-panel { padding: 12px !important; background: #fff; min-height: 260px; display:flex; flex-direction:column; gap:12px; }
.convert-btn button { height:56px!important; font-size:18px!important; font-weight:700!important; }
.logs-frame { padding:12px!important; background:#fff; }

#clear_btn button,
#clear_btn .gr-button,
#clear_btn button:hover,
#clear_btn .gr-button:hover {
  height:56px!important;
  font-size:18px!important;
  font-weight:700!important;
  background:#ff0000!important;
  color:#ffffff!important;
  border:1px solid #ff0000!important;
}
#clear_btn button:hover,
#clear_btn .gr-button:hover {
  background:#cc0000!important;
}
"""

with gr.Blocks(css=CSS, title="File Converter") as demo:
    last_output = gr.State("")

    gr.Markdown("## File Converter")

    with gr.Row(equal_height=True):
        with gr.Column(scale=5, elem_classes=["frame"]):
            inp = gr.File(label="Drop files or ZIPs", file_count="multiple")

        with gr.Column(scale=2, elem_classes=["center-panel"]):
            target = gr.Dropdown(
                label="Output format",
                choices=sorted({t for v in CONVERSION_MATRIX.values() for t in v}),
                value="pdf",
            )
            btn = gr.Button("➡ Convert", elem_classes=["convert-btn"])
            clear_btn = gr.Button("Clear", elem_id="clear_btn")

        with gr.Column(scale=5, elem_classes=["frame"]):
            out_file = gr.File(label="Result")

    with gr.Row():
        with gr.Column(elem_classes=["logs-frame"]):
            logs = gr.Textbox(label="Logs", lines=10)

    btn.click(convert, inputs=[inp, target], outputs=[out_file, logs, last_output])
    clear_btn.click(clear_all, inputs=[last_output], outputs=[inp, out_file, logs, last_output])

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7000,
        share=False,
        show_api=False,
        quiet=True,
    )