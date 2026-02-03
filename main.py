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

def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout)
    return p.stdout

def convert(file_obj, target: str):
    if file_obj is None:
        return None, "❌ Aucun fichier", ""

    src_path = Path(file_obj)
    job_id = str(uuid.uuid4())[:8]
    src_ext = src_path.suffix.lower().lstrip(".") or "bin"

    in_path = UPLOADS / f"{job_id}.{src_ext}"
    shutil.copy(src_path, in_path)

    # default output
    out_path = OUTPUTS / f"{job_id}.{target}"

    logs = ""
    try:
        if target in ["png", "jpg", "webp", "tiff"]:
            logs = run(["magick", str(in_path), str(out_path)])

        elif target in ["mp4", "webm", "mp3", "wav", "mkv"]:
            logs = run(["ffmpeg", "-y", "-i", str(in_path), str(out_path)])

        elif target == "pdf":
            tmp_out_dir = OUTPUTS / f"{job_id}_lo"
            tmp_out_dir.mkdir(parents=True, exist_ok=True)

            logs = run([
                "soffice", "--headless", "--nologo", "--nofirststartwizard",
                "--convert-to", "pdf",
                "--outdir", str(tmp_out_dir),
                str(in_path)
            ])
            produced = next(tmp_out_dir.glob("*.pdf"), None)
            if not produced:
                raise RuntimeError("LibreOffice n'a pas généré de PDF.")
            shutil.move(str(produced), str(out_path))
            shutil.rmtree(tmp_out_dir, ignore_errors=True)

        elif target == "ocrpdf":
            out_path = OUTPUTS / f"{job_id}.pdf"
            logs = run(["ocrmypdf", "--skip-text", str(in_path), str(out_path)])

        else:
            raise RuntimeError(f"Conversion vers '{target}' non supportée.")

        return str(out_path), f"✅ Terminé: {out_path.name}", logs

    except Exception as e:
        return None, f"❌ Erreur: {e}", logs


CSS = """
/* Largeur globale */
.gradio-container { max-width: 1200px !important; }

/* Titres des "blocs" style encadré */
.block-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

/* Cadres épais type schéma */
.frame {
  padding: 12px !important;
  background: #fff;
  min-height: 260px;
}

/* Colonne centrale compacte */
.center-panel {
  padding: 12px !important;
  background: #fff;
  min-height: 260px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  justify-content: flex-start;
}

/* Gros bouton conversion */
.convert-btn button {
  height: 56px !important;
  font-size: 18px !important;
  font-weight: 700 !important;
}

/* Zone logs */
.logs-frame {
  padding: 12px !important;
  background: #fff;
}

/* Responsive : sur mobile on empile */
@media (max-width: 900px) {
  .gradio-container { max-width: 95vw !important; }
}
"""

with gr.Blocks(css=CSS, title="File Converter") as demo:
    gr.Markdown("## Convertisseur de fichiers", elem_id="title")

    # Top row: left | center | right
    with gr.Row(equal_height=True):
        # LEFT
        with gr.Column(scale=5, elem_classes=["frame"]):
            #gr.Markdown("**Fichier / dossier**", elem_classes=["block-title"])
            inp = gr.File(label="Dépose un fichier", file_count="single")

        # CENTER
        with gr.Column(scale=2, elem_classes=["center-panel"]):
            #gr.Markdown("**Format de sortie**", elem_classes=["block-title"])
            target = gr.Dropdown(
                label="Format de sortie",
                choices=["png","jpg","webp","tiff","mp4","webm","mp3","wav","mkv","pdf","ocrpdf"],
                value="pdf"
            )
            btn = gr.Button("➡ Convertir", elem_classes=["convert-btn"])
            #status = gr.Textbox(label="Statut", lines=2)

        # RIGHT
        with gr.Column(scale=5, elem_classes=["frame"]):
            #gr.Markdown("**Fichier / dossier convertis**", elem_classes=["block-title"])
            out_file = gr.File(label="Résultat")

    # Bottom logs
    with gr.Row():
        with gr.Column(elem_classes=["logs-frame"]):
            #gr.Markdown("**Logs**", elem_classes=["block-title"])
            logs = gr.Textbox(label="Logs", lines=10)

    # btn.click(convert, inputs=[inp, target], outputs=[out_file, status, logs])
    btn.click(convert, inputs=[inp, target], outputs=[out_file, logs])

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7000,
        share=False,
        show_api=False,
        quiet=True
    )