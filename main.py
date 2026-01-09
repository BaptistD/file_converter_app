import os
import shutil
import subprocess
import uuid
from pathlib import Path

import gradio as gr

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
UPLOADS = DATA_DIR / "uploads"
OUTPUTS = DATA_DIR / "outputs"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

def run(cmd: list[str]) -> None:
    # Lance une commande et lève une erreur si ça échoue
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout)

def convert(file_obj, target: str):
    # file_obj est un fichier temporaire donné par Gradio
    src_path = Path(file_obj)
    job_id = str(uuid.uuid4())[:8]

    # Conserver l'extension d'origine
    src_ext = src_path.suffix.lower().lstrip(".")
    in_path = UPLOADS / f"{job_id}.{src_ext}"
    shutil.copy(src_path, in_path)

    # Output
    out_path = OUTPUTS / f"{job_id}.{target}"

    # Routage simple selon target
    try:
        if target in ["png", "jpg", "webp", "tiff"]:
            # ImageMagick: convert input output
            run(["magick", str(in_path), str(out_path)])

        elif target in ["mp4", "webm", "mp3", "wav", "mkv"]:
            # FFmpeg conversion basique
            # (tu pourras ajouter des options qualité après)
            run(["ffmpeg", "-y", "-i", str(in_path), str(out_path)])

        elif target == "pdf":
            # LibreOffice headless pour docs -> pdf
            # Pour docx/pptx/xlsx/odt/odp/ods etc.
            tmp_out_dir = OUTPUTS / f"{job_id}_lo"
            tmp_out_dir.mkdir(parents=True, exist_ok=True)
            run([
                "soffice", "--headless", "--nologo", "--nofirststartwizard",
                "--convert-to", "pdf",
                "--outdir", str(tmp_out_dir),
                str(in_path)
            ])
            # LibreOffice garde le nom original -> on récupère le pdf généré
            produced = next(tmp_out_dir.glob("*.pdf"), None)
            if not produced:
                raise RuntimeError("LibreOffice n'a pas généré de PDF.")
            shutil.move(str(produced), str(out_path))
            shutil.rmtree(tmp_out_dir, ignore_errors=True)

        elif target == "ocrpdf":
            # OCRmyPDF: input.pdf -> output.pdf (nécessite que l'entrée soit un PDF)
            # Si tu upload un non-PDF, ça échoue (normal).
            out_path = OUTPUTS / f"{job_id}.pdf"
            run(["ocrmypdf", "--skip-text", str(in_path), str(out_path)])

        else:
            raise RuntimeError(f"Conversion vers '{target}' non supportée.")

        return str(out_path), f"✅ Terminé: {out_path.name}"

    except Exception as e:
        return None, f"❌ Erreur: {e}"

with gr.Blocks(title="Local File Converter") as demo:
    gr.Markdown("# Convertisseur de fichiers (local)\nDépose un fichier, choisis un format, récupère le résultat.")
    inp = gr.File(label="Fichier à convertir")
    target = gr.Dropdown(
        label="Format cible",
        choices=["png", "jpg", "webp", "tiff", "mp4", "webm", "mp3", "wav", "mkv", "pdf", "ocrpdf"],
        value="pdf"
    )
    out_file = gr.File(label="Fichier converti")
    status = gr.Textbox(label="Statut", lines=3)
    btn = gr.Button("Convertir")

    btn.click(convert, inputs=[inp, target], outputs=[out_file, status])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=8080)