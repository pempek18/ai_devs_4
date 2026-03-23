"""
Video Generation Agent (Python)
Odzwierciedla działanie 01_04_video_generation: generowanie klatek obrazem (Gemini)
i wideo (Replicate/Kling). Klucz API Gemini z .env (GEMINI_API_KEY).
"""

import base64
import json
import os
import re
import time
from pathlib import Path

import replicate
import requests
from dotenv import load_dotenv

# Ładuj .env z katalogu głównego repozytorium
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
REPLICATE_API_TOKEN = (os.getenv("REPLICATE_API_TOKEN") or "").strip()

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE = PROJECT_ROOT / "workspace"
OUTPUT_DIR = WORKSPACE / "output"
PROMPTS_DIR = WORKSPACE / "prompts"
TEMPLATE_PATH = WORKSPACE / "template.json"

# Model do generowania obrazu (Gemini); endpoint jak w 01_04_video_generation
GEMINI_IMAGE_MODEL = "gemini-2.0-flash-exp-image-generation"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_GENERATECONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models"
KLING_MODEL = "kwaivgi/kling-v2.5-turbo-pro"


def ensure_dirs():
    """Tworzy katalogi workspace/output i workspace/prompts."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


def get_mime_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
    return mime.get(ext, "image/png")


def get_extension(mime_type: str) -> str:
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}
    return ext.get(mime_type, ".png")


# ─────────────────────────────────────────────────────────────
# Gemini – generowanie i edycja obrazu
# ─────────────────────────────────────────────────────────────


def _build_image_config(aspect_ratio: str = "16:9", image_size: str = "2k") -> dict | None:
    size = f"{image_size[:-1]}K" if image_size and image_size.endswith("k") else image_size
    return {
        "aspect_ratio": aspect_ratio,
        "image_size": size,
    }


def _gemini_generate_image(prompt: str, reference_images: list[dict] | None = None,
                           aspect_ratio: str = "16:9", image_size: str = "2k") -> tuple[bytes, str]:
    """
    Generuje obraz przez Gemini (API interactions jak w 01_04_video_generation).
    Gdy interactions nie zwróci obrazu, próbuje generateContent.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("Brak GEMINI_API_KEY w .env – dodaj klucz API Gemini.")

    config = _build_image_config(aspect_ratio, image_size)
    gen_config = {"image_config": config} if config else None

    # Wejście: sam tekst lub tekst + obrazy (edycja)
    if reference_images:
        payload_input = [
            {"type": "text", "text": prompt},
            *[{"type": "image", "data": r["data"], "mime_type": r["mime_type"]} for r in reference_images],
        ]
    else:
        payload_input = prompt

    body = {
        "model": GEMINI_IMAGE_MODEL,
        "input": payload_input,
        "response_modalities": ["IMAGE"],
    }
    if gen_config:
        body["generation_config"] = gen_config

    resp = requests.post(
        GEMINI_INTERACTIONS_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=body,
        timeout=120,
    )
    data = resp.json()

    if not resp.ok or data.get("error"):
        err = data.get("error", {})
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Gemini image request failed: {msg}")

    # Odpowiedź interactions: outputs[] z type "image"
    outputs = data.get("outputs") or []
    for out in outputs:
        if out.get("type") == "image":
            b64 = out.get("data", "")
            mime = out.get("mime_type", "image/png")
            return base64.b64decode(b64), mime

    # Fallback: generateContent (niektóre modele zwracają obraz tu)
    url = f"{GEMINI_GENERATECONTENT_URL}/{GEMINI_IMAGE_MODEL}:generateContent"
    parts = [{"text": prompt}]
    if reference_images:
        for ref in reference_images:
            parts.append({
                "inline_data": {"mime_type": ref["mime_type"], "data": ref["data"]},
            })
    body2 = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "responseMimeType": "image/png",
        },
    }
    if config:
        body2["generationConfig"] = body2.get("generationConfig", {}) | {"imageConfig": config}
    r2 = requests.post(url, headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}, json=body2, timeout=120)
    r2.raise_for_status()
    d2 = r2.json()
    if d2.get("error"):
        raise RuntimeError(d2["error"].get("message", str(d2["error"])))
    for part in (d2.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            inline = part["inlineData"]
            return base64.b64decode(inline["data"]), inline.get("mimeType", "image/png")
    raise RuntimeError("W odpowiedzi Gemini nie ma obrazu.")


def create_image(
    prompt: str,
    output_name: str,
    reference_images: list[str] | None = None,
    aspect_ratio: str = "16:9",
    image_size: str = "2k",
) -> dict:
    """
    Generuje lub edytuje obraz (Gemini).
    reference_images: list ścieżek do obrazów (np. start frame przy generowaniu end frame).
    """
    ensure_dirs()
    refs = []
    if reference_images:
        for p in reference_images:
            path = PROJECT_ROOT / p if not Path(p).is_absolute() else Path(p)
            path = path if path.is_absolute() else (PROJECT_ROOT / p)
            raw = path.read_bytes()
            refs.append({"data": base64.b64encode(raw).decode(), "mime_type": get_mime_type(str(p))})

    try:
        raw_bytes, mime_type = _gemini_generate_image(
            prompt, refs if refs else None, aspect_ratio, image_size
        )
    except Exception as e:
        return {"success": False, "error": str(e)}

    ext = get_extension(mime_type)
    filename = f"{output_name}_{int(time.time())}{ext}"
    out_path = OUTPUT_DIR / filename
    out_path.write_bytes(raw_bytes)
    relative = f"workspace/output/{filename}"
    print(f"[OK] Obraz zapisany: {relative}")
    return {
        "success": True,
        "output_path": relative,
        "absolute_path": str(out_path),
        "mime_type": mime_type,
    }


# ─────────────────────────────────────────────────────────────
# Replicate (Kling) – wideo z tekstu lub z klatki
# ─────────────────────────────────────────────────────────────


def _extract_replicate_url(out) -> str:
    """Wyciąga URL wideo z wyniku replicate.run()."""
    if isinstance(out, str):
        return out
    if hasattr(out, "url"):
        u = getattr(out, "url", None)
        return u() if callable(u) else u
    if isinstance(out, (list, tuple)) and len(out) > 0:
        first = out[0]
        if isinstance(first, str):
            return first
        if hasattr(first, "url"):
            u = getattr(first, "url", None)
            return u() if callable(u) else u
    raise ValueError("Nie można odczytać URL z wyniku Replicate")


def generate_video(
    prompt: str,
    output_name: str,
    duration: int = 10,
    aspect_ratio: str = "16:9",
    negative_prompt: str = "",
) -> dict:
    """Generuje wideo z samego opisu (Kling)."""
    ensure_dirs()
    if not REPLICATE_API_TOKEN:
        return {"success": False, "error": "Brak REPLICATE_API_TOKEN w .env."}
    try:
        out = replicate.run(
            KLING_MODEL,
            input={
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "negative_prompt": negative_prompt or "",
            },
        )
        url = _extract_replicate_url(out)
        return _download_video(url, output_name, prompt=prompt, duration=duration)
    except Exception as e:
        return {"success": False, "error": str(e)}


def image_to_video(
    prompt: str,
    start_image: str,
    output_name: str,
    end_image: str | None = None,
    duration: int = 10,
    negative_prompt: str = "",
) -> dict:
    """Generuje wideo z klatki startowej (i opcjonalnie końcowej) – Kling."""
    ensure_dirs()
    start_path = PROJECT_ROOT / start_image if not Path(start_image).is_absolute() else Path(start_image)
    if not start_path.exists():
        start_path = PROJECT_ROOT / start_image
    if not start_path.exists():
        return {"success": False, "error": f"Nie znaleziono pliku: {start_image}"}

    if not REPLICATE_API_TOKEN:
        return {"success": False, "error": "Brak REPLICATE_API_TOKEN w .env."}
    try:
        with open(start_path, "rb") as f:
            start_data = f.read()

        input_payload = {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": "16:9",
            "negative_prompt": negative_prompt or "",
            "start_image": start_data,
        }
        if end_image:
            end_path = PROJECT_ROOT / end_image if not Path(end_image).is_absolute() else Path(end_image)
            if end_path.exists():
                with open(end_path, "rb") as f:
                    input_payload["end_image"] = f.read()

        out = replicate.run(KLING_MODEL, input=input_payload)
        url = _extract_replicate_url(out)
        return _download_video(
            url, output_name, prompt=prompt, start_image=start_image, end_image=end_image, duration=duration
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


def _download_video(url: str, output_name: str, **meta) -> dict:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    filename = f"{output_name}_{int(time.time())}.mp4"
    out_path = OUTPUT_DIR / filename
    out_path.write_bytes(r.content)
    relative = f"workspace/output/{filename}"
    print(f"[OK] Wideo zapisane: {relative}")
    return {
        "success": True,
        "output_path": relative,
        "video_url": url,
        **meta,
    }


# ─────────────────────────────────────────────────────────────
# Szablon JSON (jak w 01_04_video_generation)
# ─────────────────────────────────────────────────────────────


def load_template() -> dict:
    """Ładuje template z workspace lub z przykładu 01_04_video_generation."""
    if TEMPLATE_PATH.exists():
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    example = REPO_ROOT / "01_04_video_generation" / "workspace" / "template.json"
    if example.exists():
        return json.loads(example.read_text(encoding="utf-8"))
    return {
        "subject": {"main": "", "details": "", "orientation": "three-quarter view", "position": "centered", "scale": "60% frame height"},
        "style": {"medium": "Hand-drawn pencil sketch with selective watercolor"},
        "technical": {"resolution": "2k", "aspect_ratio": "16:9"},
    }


def prompt_from_template(subject_description: str) -> str:
    """Tworzy prompt z szablonu, wypełniając sekcję subject."""
    t = load_template()
    t["subject"]["main"] = subject_description
    if not t["subject"].get("details"):
        t["subject"]["details"] = subject_description
    return json.dumps(t, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# REPL – prosty interaktywny agent (jak w przykładzie JS)
# ─────────────────────────────────────────────────────────────


def run_repl():
    """Pętla REPL: użytkownik podaje opis sceny → generowana jest klatka startowa i wideo."""
    if not GEMINI_API_KEY:
        print("Błąd: Ustaw GEMINI_API_KEY w pliku .env w katalogu głównym repozytorium.")
        return
    if not REPLICATE_API_TOKEN:
        print("Błąd: Ustaw REPLICATE_API_TOKEN w pliku .env.")
        return

    ensure_dirs()
    print("Video Generation Agent (Python) – Gemini (obraz) + Replicate/Kling (wideo)")
    print("Wpisz opis sceny (np. 'rudy lis skacze w śnieg'), 'exit' aby wyjść.\n")

    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            continue
        if user.lower() == "exit":
            break

        scene = re.sub(r"\W+", "_", user.lower())[:30] or "scene"
        ts = int(time.time())
        base_name = f"{scene}_{ts}"

        # 1) Klatka startowa (Gemini)
        prompt_json = prompt_from_template(user)
        print("[*] Generuję klatkę startową (Gemini)...")
        start_result = create_image(
            prompt=prompt_json,
            output_name=f"{base_name}_frame_start",
            reference_images=[],
            aspect_ratio="16:9",
            image_size="2k",
        )
        if not start_result.get("success"):
            print(f"Błąd klatki: {start_result.get('error', 'unknown')}")
            continue
        start_path = start_result["output_path"]

        # 2) Wideo z klatki (Kling)
        motion_prompt = f"Płynna animacja: {user}"
        print("[*] Generuję wideo (Kling)...")
        video_result = image_to_video(
            prompt=motion_prompt,
            start_image=start_path,
            output_name=f"{base_name}_video",
            duration=10,
        )
        if not video_result.get("success"):
            print(f"Błąd wideo: {video_result.get('error', 'unknown')}")
            continue
        print(f"\nAssistant: Gotowe. Klatka: {start_path}, wideo: {video_result['output_path']}\n")


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "repl":
        run_repl()
        return
    # Jednorazowe wywołanie: python app.py "opis sceny"
    if len(sys.argv) > 1:
        prompt_text = " ".join(sys.argv[1:])
        scene = re.sub(r"\W+", "_", prompt_text.lower())[:30] or "scene"
        ts = int(time.time())
        base = f"{scene}_{ts}"
        prompt_json = prompt_from_template(prompt_text)
        r1 = create_image(prompt_json, f"{base}_frame_start", aspect_ratio="16:9", image_size="2k")
        if not r1.get("success"):
            print(r1.get("error"))
            sys.exit(1)
        r2 = image_to_video(f"Płynna animacja: {prompt_text}", r1["output_path"], f"{base}_video", duration=10)
        if not r2.get("success"):
            print(r2.get("error"))
            sys.exit(1)
        print("Klatka:", r1["output_path"], "| Wideo:", r2["output_path"])
        return
    run_repl()


if __name__ == "__main__":
    main()
