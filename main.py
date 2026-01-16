# import os
# import shutil
# import subprocess
# import uuid
# from pathlib import Path

# import gradio as gr

# DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
# UPLOADS = DATA_DIR / "uploads"
# OUTPUTS = DATA_DIR / "outputs"
# UPLOADS.mkdir(parents=True, exist_ok=True)
# OUTPUTS.mkdir(parents=True, exist_ok=True)

# def run(cmd: list[str]) -> None:
#     # Lance une commande et lève une erreur si ça échoue
#     p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
#     if p.returncode != 0:
#         raise RuntimeError(p.stdout)

# def convert(file_obj, target: str):
#     # file_obj est un fichier temporaire donné par Gradio
#     src_path = Path(file_obj)
#     job_id = str(uuid.uuid4())[:8]

#     # Conserver l'extension d'origine
#     src_ext = src_path.suffix.lower().lstrip(".")
#     in_path = UPLOADS / f"{job_id}.{src_ext}"
#     shutil.copy(src_path, in_path)

#     # Output
#     out_path = OUTPUTS / f"{job_id}.{target}"

#     # Routage simple selon target
#     try:
#         if target in ["png", "jpg", "webp", "tiff"]:
#             # ImageMagick: convert input output
#             run(["magick", str(in_path), str(out_path)])

#         elif target in ["mp4", "webm", "mp3", "wav", "mkv"]:
#             # FFmpeg conversion basique
#             # (tu pourras ajouter des options qualité après)
#             run(["ffmpeg", "-y", "-i", str(in_path), str(out_path)])

#         elif target == "pdf":
#             # LibreOffice headless pour docs -> pdf
#             # Pour docx/pptx/xlsx/odt/odp/ods etc.
#             tmp_out_dir = OUTPUTS / f"{job_id}_lo"
#             tmp_out_dir.mkdir(parents=True, exist_ok=True)
#             run([
#                 "soffice", "--headless", "--nologo", "--nofirststartwizard",
#                 "--convert-to", "pdf",
#                 "--outdir", str(tmp_out_dir),
#                 str(in_path)
#             ])
#             # LibreOffice garde le nom original -> on récupère le pdf généré
#             produced = next(tmp_out_dir.glob("*.pdf"), None)
#             if not produced:
#                 raise RuntimeError("LibreOffice did not generate a PDF.")
#             shutil.move(str(produced), str(out_path))
#             shutil.rmtree(tmp_out_dir, ignore_errors=True)

#         elif target == "ocrpdf":
#             # OCRmyPDF: input.pdf -> output.pdf (nécessite que l'entrée soit un PDF)
#             # Si tu upload un non-PDF, ça échoue (normal).
#             out_path = OUTPUTS / f"{job_id}.pdf"
#             run(["ocrmypdf", "--skip-text", str(in_path), str(out_path)])

#         else:
#             raise RuntimeError(f"Convert to '{target}' not supported.")

#         return str(out_path), f"✅ Completed: {out_path.name}"

#     except Exception as e:
#         return None, f"❌ Error: {e}"

# with gr.Blocks(title="Local File Converter") as demo:
#     gr.Markdown("# File Converter\n Put a file or folder, choose a format, get the result.")
#     inp = gr.File(label="File to convert")
#     target = gr.Dropdown(
#         label="Target format",
#         choices=["png", "jpg", "webp", "tiff", "mp4", "webm", "mp3", "wav", "mkv", "pdf", "ocrpdf"],
#         value="pdf"
#     )
#     out_file = gr.File(label="Converted file")
#     status = gr.Textbox(label="Status", lines=3)
#     btn = gr.Button("Convert")

#     btn.click(convert, inputs=[inp, target], outputs=[out_file, status])

# # if __name__ == "__main__":
# #     demo.launch(server_name="0.0.0.0", server_port=7000)

# if __name__ == "__main__":
#     demo.launch(
#         server_name="0.0.0.0",
#         server_port=7000,
#         share=False,
#         show_api=False,
#         quiet=True,
#         allowed_paths=[str(OUTPUTS)]
#     )


import os
import shutil
import subprocess
import uuid
from pathlib import Path
from datetime import datetime

import gradio as gr

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
UPLOADS = DATA_DIR / "uploads"
OUTPUTS = DATA_DIR / "outputs"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

def run(cmd: list[str]) -> str:
    """Run command and return combined output; raise on error."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout)
    return p.stdout

def list_outputs(limit: int = 30):
    files = sorted(OUTPUTS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for p in files[:limit]:
        ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        rows.append([p.name, ts, f"{p.stat().st_size/1024:.1f} KB", str(p)])
    return rows

def convert(file_obj, category: str, target: str, img_quality: int, video_preset: str, ocr_lang: str):
    if file_obj is None:
        return None, "❌ Aucun fichier", ""

    src_path = Path(file_obj)
    job_id = str(uuid.uuid4())[:8]
    src_ext = src_path.suffix.lower().lstrip(".") or "bin"
    in_path = UPLOADS / f"{job_id}.{src_ext}"
    shutil.copy(src_path, in_path)

    logs = []
    status = "OK"

    try:
        # Output path
        out_ext = target
        if target == "ocrpdf":
            out_ext = "pdf"
        out_path = OUTPUTS / f"{job_id}.{out_ext}"

        if category == "Image":
            # ImageMagick: quality only affects some formats (webp/jpg)
            cmd = ["magick", str(in_path)]
            if target in ["webp", "jpg", "jpeg"]:
                cmd += ["-quality", str(img_quality)]
            cmd += [str(out_path)]
            logs.append(run(cmd))

        elif category == "Vidéo/Audio":
            # Basic ffmpeg preset (simple; we’ll improve later)
            # preset: ultrafast/fast/medium/slow
            cmd = ["ffmpeg", "-y", "-i", str(in_path)]
            if target in ["mp4", "mkv", "webm"]:
                cmd += ["-preset", video_preset]
            cmd += [str(out_path)]
            logs.append(run(cmd))

        elif category == "Document":
            tmp_out_dir = OUTPUTS / f"{job_id}_lo"
            tmp_out_dir.mkdir(parents=True, exist_ok=True)
            logs.append(run([
                "soffice", "--headless", "--nologo", "--nofirststartwizard",
                "--convert-to", "pdf",
                "--outdir", str(tmp_out_dir),
                str(in_path)
            ]))
            produced = next(tmp_out_dir.glob("*.pdf"), None)
            if not produced:
                raise RuntimeError("LibreOffice n'a pas généré de PDF.")
            shutil.move(str(produced), str(out_path))
            shutil.rmtree(tmp_out_dir, ignore_errors=True)

        elif category == "PDF":
            if target == "ocrpdf":
                # OCR (language)
                logs.append(run([
                    "ocrmypdf", "--skip-text", "-l", ocr_lang,
                    str(in_path), str(out_path)
                ]))
            elif target in ["png", "jpg"]:
                # PDF -> images (first page only for now)
                # You can expand later to zip all pages.
                out_path = OUTPUTS / f"{job_id}.{target}"
                cmd = ["pdftoppm", "-singlefile", f"-{target}", str(in_path), str(OUTPUTS / job_id)]
                logs.append(run(cmd))
                # pdftoppm writes OUTPUTS/job_id.<ext>
                produced = OUTPUTS / f"{job_id}.{target}"
                if produced.exists():
                    out_path = produced
                else:
                    raise RuntimeError("Conversion PDF -> image échouée.")
            else:
                raise RuntimeError("Cible PDF non supportée.")

        else:
            raise RuntimeError("Catégorie inconnue.")

        return str(out_path), f"✅ Terminé: {out_path.name}", "\n".join(logs)

    except Exception as e:
        status = f"❌ Erreur: {e}"
        return None, status, "\n".join(logs)

def targets_for_category(category: str):
    if category == "Image":
        return gr.Dropdown(choices=["png","jpg","webp","tiff"], value="webp"), gr.Row(visible=True), gr.Row(visible=False), gr.Row(visible=False)
    if category == "Vidéo/Audio":
        return gr.Dropdown(choices=["mp4","webm","mp3","wav","mkv"], value="mp4"), gr.Row(visible=False), gr.Row(visible=True), gr.Row(visible=False)
    if category == "Document":
        return gr.Dropdown(choices=["pdf"], value="pdf"), gr.Row(visible=False), gr.Row(visible=False), gr.Row(visible=False)
    if category == "PDF":
        return gr.Dropdown(choices=["ocrpdf","png","jpg"], value="ocrpdf"), gr.Row(visible=False), gr.Row(visible=False), gr.Row(visible=True)
    return gr.Dropdown(choices=["pdf"], value="pdf"), gr.Row(visible=False), gr.Row(visible=False), gr.Row(visible=False)

# with gr.Blocks(title="File Converter (Local)") as demo:
#     gr.Markdown("## Convertisseur de fichiers (local)\nUI améliorée + logs + historique.")

#     with gr.Tabs():
#         with gr.Tab("Convertir"):
#             with gr.Row():
#                 inp = gr.File(label="Dépose ton fichier", file_count="single")
#                 with gr.Column():
#                     category = gr.Radio(["Image", "Vidéo/Audio", "Document", "PDF"], value="Document", label="Catégorie")

#                     target = gr.Dropdown(label="Format cible", choices=["pdf"], value="pdf")

#                     with gr.Row(visible=False) as img_opts:
#                         img_quality = gr.Slider(1, 100, value=85, step=1, label="Qualité (JPG/WebP)")

#                     with gr.Row(visible=False) as vid_opts:
#                         video_preset = gr.Dropdown(["ultrafast","fast","medium","slow"], value="medium", label="Preset encodage")

#                     with gr.Row(visible=False) as pdf_opts:
#                         ocr_lang = gr.Dropdown(["eng","fra","deu","spa","ita"], value="fra", label="Langue OCR")

#                     btn = gr.Button("Convertir")

#             out_file = gr.File(label="Résultat")
#             status = gr.Textbox(label="Statut", lines=2)
#             logs = gr.Textbox(label="Logs", lines=10)

#             category.change(
#                 targets_for_category,
#                 inputs=[category],
#                 outputs=[target, img_opts, vid_opts, pdf_opts]
#             )

#             btn.click(
#                 convert,
#                 inputs=[inp, category, target,
#                         gr.State(85),  # placeholder (replaced below)
#                         gr.State("medium"),
#                         gr.State("fra")],
#                 outputs=[out_file, status, logs]
#             )

#             # Wire real option widgets to click (Gradio limitation workaround: use same function signature)
#             btn.click(
#                 convert,
#                 inputs=[inp, category, target, img_quality, video_preset, ocr_lang],
#                 outputs=[out_file, status, logs]
#             )

#         with gr.Tab("Historique"):
#             refresh = gr.Button("Rafraîchir")
#             table = gr.Dataframe(headers=["Fichier", "Date", "Taille", "Chemin"], interactive=False)
#             refresh.click(lambda: list_outputs(50), outputs=[table])
#             demo.load(lambda: list_outputs(50), outputs=[table])

#         with gr.Tab("Réglages"):
#             gr.Markdown(
#                 "- Les fichiers uploadés vont dans `/data/uploads`\n"
#                 "- Les résultats vont dans `/data/outputs`\n"
#                 "- Prochaine étape : presets + queue + conversion multi-pages PDF"
#             )

with gr.Blocks(title="File Converter (Local)") as demo:
    gr.Markdown("## Convertisseur de fichiers (local)\nUI améliorée + logs + historique.")

    with gr.Tabs():
        with gr.Tab("Convertir"):
            with gr.Column():
                category = gr.Radio(["Image", "Vidéo/Audio", "Document", "PDF"], value="Document", label="Catégorie")

                target = gr.Dropdown(label="Format cible", choices=["pdf"], value="pdf")

                with gr.Row(visible=False) as img_opts:
                    img_quality = gr.Slider(1, 100, value=85, step=1, label="Qualité (JPG/WebP)")

                with gr.Row(visible=False) as vid_opts:
                    video_preset = gr.Dropdown(["ultrafast","fast","medium","slow"], value="medium", label="Preset encodage")

                with gr.Row(visible=False) as pdf_opts:
                    ocr_lang = gr.Dropdown(["eng","fra","deu","spa","ita"], value="fra", label="Langue OCR")

        with gr.Column():
            with gr.Row():
                inp = gr.File(label="Dépose ton fichier", file_count="single")

            with gr.Row():
                btn = gr.Button("-->")

            with gr.Row():
                out_file = gr.File(label="Résultat")


            status = gr.Textbox(label="Statut", lines=2)
            logs = gr.Textbox(label="Logs", lines=5)

            category.change(
                targets_for_category,
                inputs=[category],
                outputs=[target, img_opts, vid_opts, pdf_opts]
            )

            btn.click(
                convert,
                inputs=[inp, category, target,
                        gr.State(85),  # placeholder (replaced below)
                        gr.State("medium"),
                        gr.State("fra")],
                outputs=[out_file, status, logs]
            )

            # Wire real option widgets to click (Gradio limitation workaround: use same function signature)
            btn.click(
                convert,
                inputs=[inp, category, target, img_quality, video_preset, ocr_lang],
                outputs=[out_file, status, logs]
            )

        with gr.Tab("Historique"):
            refresh = gr.Button("Rafraîchir")
            table = gr.Dataframe(headers=["Fichier", "Date", "Taille", "Chemin"], interactive=False)
            refresh.click(lambda: list_outputs(50), outputs=[table])
            demo.load(lambda: list_outputs(50), outputs=[table])

        with gr.Tab("Réglages"):
            gr.Markdown(
                "- Les fichiers uploadés vont dans `/data/uploads`\n"
                "- Les résultats vont dans `/data/outputs`\n"
                "- Prochaine étape : presets + queue + conversion multi-pages PDF"
            )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7000,
        share=False,
        show_api=False,
        quiet=True,
    )