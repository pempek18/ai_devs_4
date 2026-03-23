"""
Zadanie electricity (hub): plansza 3x3 — obrót pól o 90° w prawo, aż układ kabli
zgodny ze schematem docelowym (solved_electricity.png).

Uruchomienie:
  python app.py                 # agent + function calling (domyslnie)
  python app.py --legacy        # jednorazowy plan + obroty (stary tryb)
  python app.py --legacy --heuristic
  python app.py --reset

Agent: model tekstowy widzi wyniki narzedzi. Wizja zwraca JSON z polem cells (3x3 obiekty na komorke:
id, n,e,s,w, brief) — to samo trafia do narzedzi i agenta.

.env: HUB_API_KEY (wymagane). Wizja: GEMINI_API_KEY (Google AI) i/lub OPENAI_API_KEY.
ELECTRICITY_VISION_PROVIDER=auto|gemini|openai — ktory backend wizji (auto: Gemini jesli jest GEMINI_API_KEY).
ELECTRICITY_GEMINI_MODEL — np. gemini-2.0-flash (bezposrednio API Google).
ELECTRICITY_OPENAI_VISION_MODEL — np. gpt-4o-mini (bezposrednio api.openai.com).
ELECTRICITY_VISION_JSON_MODE=1 — JSON mode (OpenAI: response_format; Gemini: responseMimeType).
ELECTRICITY_VISION_MAX_OUTPUT — max tokenow WYJSCIA Gemini (domyslnie 2048; JSON 3x3 nie potrzebuje 8k).
GEMINI_VISION_IMAGE_MAX_EDGE — max dluzszy bok w px przed wyslaniem do Gemini (domyslnie 384: jedna plytka
  wizji ~258 tokenow wg dokumentacji API; 0 / none = bez skalowania, oryginalny plik).
GEMINI_VISION_JPEG_QUALITY — 1-95, domyslnie 85 (tylko gdy obraz jest kodowany do JPEG).
ELECTRICITY_OPENAI_VISION_MAX_TOKENS — limit wyjscia OpenAI wizji (domyslnie 2048).
ELECTRICITY_AGENT_MODEL — model agenta (tylko OpenAI, np. gpt-4o-mini).
ELECTRICITY_VISION_FALLBACK_OPENAI_ON_429=1 — przy limicie Gemini (429) automatycznie wizja przez OpenAI (jesli jest klucz).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple

import numpy as np
import requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

HUB_API_KEY = os.getenv("HUB_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VERIFY_URL = "https://hub.ag3nts.org/verify"
SOLVED_PNG_URL = "https://hub.ag3nts.org/i/solved_electricity.png"

# Bezposrednio Google Generative Language API (nie OpenRouter).
DEFAULT_GEMINI_VISION_MODEL = os.getenv("ELECTRICITY_GEMINI_MODEL", "gemini-2.0-flash")
DEFAULT_OPENAI_MODEL = os.getenv("ELECTRICITY_OPENAI_VISION_MODEL", "gpt-4o-mini")
DEFAULT_AGENT_MODEL = os.getenv("ELECTRICITY_AGENT_MODEL", "gpt-4o-mini")


def _vision_wants_json_object_mode() -> bool:
    """ELECTRICITY_VISION_JSON_MODE=1 — wymusza tryb JSON (OpenAI / Gemini)."""
    v = os.getenv("ELECTRICITY_VISION_JSON_MODE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _vision_response_format_block_openai() -> dict[str, Any]:
    if not _vision_wants_json_object_mode():
        return {}
    return {"response_format": {"type": "json_object"}}


def _vision_provider() -> str:
    """auto | gemini | openai."""
    p = os.getenv("ELECTRICITY_VISION_PROVIDER", "auto").strip().lower()
    if p in ("auto", "gemini", "openai"):
        return p
    return "auto"


def _active_vision_label() -> str:
    p = _vision_provider()
    if p == "openai":
        return f"OpenAI/{DEFAULT_OPENAI_MODEL}"
    if p == "gemini":
        return f"Gemini/{DEFAULT_GEMINI_VISION_MODEL}"
    if GEMINI_API_KEY:
        return f"Gemini/{DEFAULT_GEMINI_VISION_MODEL}"
    return f"OpenAI/{DEFAULT_OPENAI_MODEL}"


def _grid_as_dicts(grid: list[list[tuple[int, int, int, int]]]) -> list[list[dict[str, int]]]:
    return [
        [{"n": c[0], "e": c[1], "s": c[2], "w": c[3]} for c in row]
        for row in grid
    ]


def format_grid_ascii(grid: list[list[tuple[int, int, int, int]]]) -> str:
    lines = []
    for r in range(3):
        cells = []
        for c in range(3):
            n, e, s, w = grid[r][c]
            cells.append(
                ("" if not n else "N")
                + ("" if not e else "E")
                + ("" if not s else "S")
                + ("" if not w else "W")
                or "-"
            )
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def format_grid_with_row_labels(grid: list[list[tuple[int, int, int, int]]]) -> str:
    """3 wiersze z etykieta rzedu (1| 2| 3|) dla czytelnosci."""
    lines = []
    for r in range(3):
        cells = []
        for c in range(3):
            n, e, s, w = grid[r][c]
            cells.append(
                ("" if not n else "N")
                + ("" if not e else "E")
                + ("" if not s else "S")
                + ("" if not w else "W")
                or "-"
            )
        lines.append(f"rzad {r + 1}:  " + " | ".join(cells))
    return "\n".join(lines)


def compare_grids_for_agent(
    current: list[list[tuple[int, int, int, int]]],
    target: list[list[tuple[int, int, int, int]]],
) -> dict[str, Any]:
    """Porownanie do JSON dla narzedzia + logika match_complete."""
    cells_out: list[dict[str, Any]] = []
    pending: list[str] = []
    impossible: list[str] = []
    for r in range(3):
        for c in range(3):
            cur = current[r][c]
            tgt = target[r][c]
            cn = cell_name(r, c)
            k = _rotations_to_match(cur, tgt)
            cell_info: dict[str, Any] = {
                "cell": cn,
                "current_nesw": {"n": cur[0], "e": cur[1], "s": cur[2], "w": cur[3]},
                "target_nesw": {"n": tgt[0], "e": tgt[1], "s": tgt[2], "w": tgt[3]},
                "rotations_needed_cw_90": k,
            }
            if k is None:
                cell_info["status"] = "IMPOSSIBLE_TILE_TYPE"
                impossible.append(cn)
            elif k == 0:
                cell_info["status"] = "OK"
            else:
                cell_info["status"] = f"NEEDS_{k}_ROTATIONS"
                pending.append(f"{cn}({k}x)")
            cells_out.append(cell_info)
    match_complete = len(pending) == 0 and len(impossible) == 0
    return {
        "cells": cells_out,
        "match_complete": match_complete,
        "pending_rotations_summary": pending,
        "impossible_cells": impossible,
    }


def print_vision_dual_and_summary(
    current: list[list[tuple[int, int, int, int]]],
    target: list[list[tuple[int, int, int, int]]],
    *,
    header: str,
    cmp: dict[str, Any] | None = None,
) -> None:
    """Druk: dwie siatki obok siebie + krotka lista roznic (tylko konsola)."""
    if cmp is None:
        cmp = compare_grids_for_agent(current, target)
    left_lines = format_grid_with_row_labels(current).splitlines()
    right_lines = format_grid_with_row_labels(target).splitlines()
    w = max(len(x) for x in left_lines) + 1
    lt = "AKTUALNY (wizja)"
    rt = "CEL (docelowy, wizja)"
    print("")
    print(f"--- {header} ---")
    print(f"{lt.ljust(w)} | {rt}")
    print("-" * w + "-+-" + "-" * max(len(rt), 20))
    for i in range(3):
        print(f"{left_lines[i].ljust(w)} | {right_lines[i]}")
    print("")
    if cmp["match_complete"]:
        print("Porownanie: WSZYSTKIE KOMORKI ZGODNE Z CELEM (0 obrotow) -> NIE obracaj juz zadnego pola.")
    else:
        if cmp["impossible_cells"]:
            print(
                "Porownanie: BLAD TYPU KLOCKA (obrot nie wystarczy): "
                + ", ".join(cmp["impossible_cells"])
            )
        if cmp["pending_rotations_summary"]:
            print(
                "Do wykonania (tylko te pola, tyle obrotow 90 w prawo): "
                + ", ".join(cmp["pending_rotations_summary"])
            )
    print("")


VISION_SYSTEM = (
    "You read ONE 3x3 electrical pipe puzzle image split into 9 equal cells (rows 1..3 top to bottom, "
    "columns 1..3 left to right). For EACH cell separately, decide which sides have a wire to that edge "
    "(N,E,S,W = 0/1). Output ONLY a single JSON object with key grid — no global essay, no markdown. "
    "Do not describe the whole image, background color, or that it is a 3x3 grid — only per-cell facts."
)

VISION_USER = """Return exactly one JSON object with a single key grid (3x3 array of objects).

Each grid[r][c] MUST have:
- id: string AxB for that cell (grid[0][0] is 1x1, grid[2][2] is 3x3).
- n, e, s, w: integers 0 or 1 (wire to that edge of this cell).
- brief: one English sentence, max ~200 chars, ONLY about this cell: which edges have wires and shape (L/T/cross/straight).
  Do not write generic filler: no The image, no 3x3 grid, no beige background, no overall puzzle description.

Rules for n,e,s,w: 1 only if a brown/tan wire reaches the middle of that edge. Ignore PWR labels and decorations.

Output valid JSON only; escape double-quotes inside string values; no raw line breaks inside strings.

Minimal example shape:
{"grid":[[{"id":"1x1","n":0,"e":1,"s":1,"w":0,"brief":"Wire toward E and S only."},...],...]}"""


def _png_data_url(path: Path) -> str:
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _repair_llm_json(s: str) -> str:
    """Typowe uszkodzenia JSON z LLM: przecinek przed }/], cudzyslowy unicode."""
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def _slice_balanced_json_value(s: str, i: int) -> str | None:
    """Wycina jeden pelny obiekt JSON { ... } lub tablice [ ... ] od indeksu i (string-aware)."""
    if i >= len(s) or s[i] not in "{[":
        return None
    pairs = {"{": "}", "[": "]"}
    stack = [pairs[s[i]]]
    j = i + 1
    instr = False
    esc = False
    while j < len(s):
        c = s[j]
        if esc:
            esc = False
            j += 1
            continue
        if instr:
            if c == "\\":
                esc = True
            elif c == '"':
                instr = False
            j += 1
            continue
        if c == '"':
            instr = True
            j += 1
            continue
        if c in "{[":
            stack.append(pairs[c])
        elif c in "}]":
            if not stack or c != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return s[i : j + 1]
        j += 1
    return None


def _try_loads_dict(blob: str) -> dict | None:
    blob = blob.strip()
    for variant in (blob, _repair_llm_json(blob)):
        try:
            out = json.loads(variant)
            if isinstance(out, dict):
                return out
        except json.JSONDecodeError:
            continue
    return None


def _parse_dicts_from_text(text: str) -> list[dict]:
    """Probuje wyciac obiekty JSON { ... } i sparsowac (odpornie na smieci wokol)."""
    out: list[dict] = []
    dec = json.JSONDecoder()
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        sub = _slice_balanced_json_value(text, i)
        if sub:
            for cand in (sub, _repair_llm_json(sub)):
                try:
                    obj, _ = dec.raw_decode(cand, 0)
                    if isinstance(obj, dict) and "grid" in obj:
                        out.append(obj)
                        break
                except json.JSONDecodeError:
                    try:
                        obj = json.loads(cand)
                        if isinstance(obj, dict) and "grid" in obj:
                            out.append(obj)
                            break
                    except json.JSONDecodeError:
                        continue
        i += 1
    return out


def _fallback_grid_only_object(text: str) -> dict:
    """Gdy caly JSON jest zepsuty (np. nieescapowane cudzyslowy w brief), wycinamy tylko tablice grid."""
    m = re.search(r'"grid"\s*:\s*', text)
    if not m:
        raise ValueError("Brak pola grid w odpowiedzi modelu")
    i = m.end()
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    if i >= len(text) or text[i] != "[":
        raise ValueError("Brak tablicy po grid w odpowiedzi modelu")
    arr = _slice_balanced_json_value(text, i)
    if not arr:
        raise ValueError("Nie udalo sie wyciac tablicy grid")
    wrapper = '{"grid":' + arr + "}"
    for w in (wrapper, _repair_llm_json(wrapper)):
        try:
            obj = json.loads(w)
            if isinstance(obj, dict) and "grid" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("Tablica grid nadal nieparsowalna — skroc brief w komorkach lub zmien model.")


def _extract_json_object(text: str) -> dict:
    """Parsuje odpowiedz wizji: caly JSON lub — przy bledzie — samo pole grid."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Pusta odpowiedz modelu wizji")

    blocks: list[str] = [text]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        blocks.insert(0, fence.group(1).strip())

    for block in blocks:
        got = _try_loads_dict(block)
        if got and "grid" in got:
            return got
        for d in _parse_dicts_from_text(block):
            if "grid" in d:
                return d

    for block in blocks:
        repaired = _repair_llm_json(block)
        got = _try_loads_dict(repaired)
        if got and "grid" in got:
            return got
        for d in _parse_dicts_from_text(repaired):
            if "grid" in d:
                return d

    try:
        return _fallback_grid_only_object(text)
    except ValueError:
        pass
    try:
        return _fallback_grid_only_object(_repair_llm_json(text))
    except ValueError as e:
        raise ValueError(
            "Nie udalo sie sparsowac JSON z modelu wizji. "
            "Sprobuj innego modelu (ELECTRICITY_VISION_MODEL) lub krotszego opisu w prompcie."
        ) from e


def _coerce_grid_to_3x3(raw: Any) -> list[list[Any]]:
    """
    Model wizji czesto zwraca grid inaczej niz [[a,b,c],...]: plaska lista 9 komorek,
    jeden wiersz z 9 elementami, albo obiekt {"1x1": {...}, ...}. Normalizujemy do 3x3.
    """
    g = raw
    if isinstance(g, str):
        try:
            g = json.loads(g)
        except json.JSONDecodeError as e:
            raise ValueError(f"grid jest stringiem, ale to nie jest poprawny JSON: {e}") from e

    if isinstance(g, dict):
        mat: list[list[Any]] = [[None, None, None], [None, None, None], [None, None, None]]
        for key, cell in g.items():
            m = re.fullmatch(r"([1-3])x([1-3])", str(key).strip())
            if not m:
                continue
            r, c = int(m.group(1)) - 1, int(m.group(2)) - 1
            mat[r][c] = cell
        if any(x is None for row in mat for x in row):
            raise ValueError(
                "grid jako obiekt slownikowy: oczekiwane klucze 1x1..3x3 (wszystkie 9)."
            )
        return mat

    if not isinstance(g, list):
        raise ValueError(f"grid musi byc lista lub slownik, jest: {type(g).__name__}")

    if len(g) == 9 and all(isinstance(x, dict) for x in g):
        return [g[0:3], g[3:6], g[6:9]]

    if len(g) == 1 and isinstance(g[0], list) and len(g[0]) == 9:
        row9 = g[0]
        if not all(isinstance(x, dict) for x in row9):
            raise ValueError("9 komorek w jednym wierszu: kazda musi byc obiektem")
        return [row9[0:3], row9[3:6], row9[6:9]]

    if len(g) == 3:
        for i, row in enumerate(g):
            if isinstance(row, list) and len(row) == 9:
                if not all(isinstance(x, dict) for x in row):
                    raise ValueError(f"wiersz {i}: 9 elementow, ale nie wszystkie to obiekty")
                return [row[0:3], row[3:6], row[6:9]]
            if not isinstance(row, list):
                raise ValueError(f"wiersz {i} nie jest lista, jest {type(row).__name__}")
            if len(row) != 3:
                raise ValueError(
                    f"wiersz {i}: oczekiwano 3 komorek (albo 9 w jednym wierszu), jest len={len(row)}"
                )
        return g

    raise ValueError(
        f"Nieznany uklad grid: len(lista)={len(g)}. "
        "Poprawny: 3 wiersze x 3 komorki LUB plaska lista 9 obiektow."
    )


def _pick_grid_payload(data: dict) -> Any:
    """Bierze grid lub cells (alias od niektorych modeli)."""
    if "grid" in data and data["grid"] is not None:
        return data["grid"]
    if "cells" in data and data["cells"] is not None:
        return data["cells"]
    return None


def _grid_from_vision_payload(data: dict) -> list[list[tuple[int, int, int, int]]]:
    raw = _pick_grid_payload(data)
    g = _coerce_grid_to_3x3(raw)
    out: list[list[tuple[int, int, int, int]]] = []
    for row in g:
        rlist: list[tuple[int, int, int, int]] = []
        for cell in row:
            if not isinstance(cell, dict):
                raise ValueError("Komorka musi byc obiektem n,e,s,w")
            rlist.append(
                (
                    int(cell["n"]),
                    int(cell["e"]),
                    int(cell["s"]),
                    int(cell["w"]),
                )
            )
        out.append(rlist)
    return out


def _infer_tile_shape(n: int, e: int, s: int, w: int) -> str:
    """Etykieta geometryczna z maski NESW (do JSON dla agenta)."""
    cnt = n + e + s + w
    if cnt == 0:
        return "blank"
    if cnt == 1:
        return "end"
    if cnt == 2:
        if n and s and not e and not w:
            return "straight_ns"
        if e and w and not n and not s:
            return "straight_ew"
        return "L"
    if cnt == 3:
        return "T"
    if cnt == 4:
        return "cross"
    return "unknown"


def _build_normalized_cells(data: dict) -> list[list[dict[str, Any]]]:
    """Kanoniczna lista komorek dla agenta (to samo co ma wizja w grid)."""
    g = data.get("grid")
    if not isinstance(g, list) or len(g) != 3:
        raise ValueError("Oczekiwano grid 3x3")
    out: list[list[dict[str, Any]]] = []
    for r in range(3):
        row = g[r]
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("Wiersz grid musi miec 3 komorki")
        rlist: list[dict[str, Any]] = []
        for c in range(3):
            addr = f"{r + 1}x{c + 1}"
            cell = row[c]
            if not isinstance(cell, dict):
                raise ValueError("Komorka musi byc obiektem JSON")
            n, e, s, w = (
                int(cell["n"]),
                int(cell["e"]),
                int(cell["s"]),
                int(cell["w"]),
            )
            brief_raw = cell.get("brief", "")
            brief = str(brief_raw).strip()[:400] if brief_raw is not None else ""
            cid = str(cell.get("id", addr)).strip() or addr
            shape = _infer_tile_shape(n, e, s, w)
            rlist.append(
                {
                    "id": cid,
                    "n": n,
                    "e": e,
                    "s": s,
                    "w": w,
                    "shape": shape,
                    "brief": brief,
                }
            )
        out.append(rlist)
    return out


class VisionBoardParse(NamedTuple):
    """Wynik wizji: siatka logiczna + te same komorki co w JSON dla agenta."""

    grid: list[list[tuple[int, int, int, int]]]
    cells: list[list[dict[str, Any]]]


def _parse_vision_full(data: dict) -> VisionBoardParse:
    """Model wizji (HTTP) juz zwrocil tresc — tu tylko normalizacja ksztaltu grid + komorki."""
    merged = dict(data)
    raw = _pick_grid_payload(merged)
    if raw is None:
        raise ValueError(
            "Odpowiedz modelu wizji nie ma pola 'grid' ani 'cells'. "
            f"To nie jest kwestia agenta tekstowego — JSON z obrazka ma klucze: {list(data.keys())!r}"
        )
    merged["grid"] = _coerce_grid_to_3x3(raw)
    grid = _grid_from_vision_payload(merged)
    cells = _build_normalized_cells(merged)
    return VisionBoardParse(grid=grid, cells=cells)


def _gemini_vision_max_edge() -> int | None:
    """Domyslnie 384 (typowo 258 tokenow na obraz — obie wymiary <= 384). None = bez skalowania."""
    raw = os.getenv("GEMINI_VISION_IMAGE_MAX_EDGE")
    if raw is None:
        return 384
    s = raw.strip().lower()
    if s in ("", "0", "none", "off", "full", "raw"):
        return None
    try:
        n = int(s)
    except ValueError:
        return 384
    return None if n <= 0 else n


def _pil_to_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        return bg
    return im.convert("RGB")


def compress_image_for_gemini_context(path: Path) -> tuple[bytes, str]:
    """
    Kompresja / normalizacja obrazu pod Gemini (np. gemini-3-flash-preview).

    Zgodnie z dokumentacja Gemini API: przy obu wymiarach <= 384 px obraz liczy sie jako
    jedna plytka (258 tokenow); wieksze obrazy sa dzielone na kafelki 768x768 (wiecej tokenow).

    - Skalowanie: max(dluzszy bok) <= GEMINI_VISION_IMAGE_MAX_EDGE (domyslnie 384); 0 = brak skalowania.
    - JPEG (image/jpeg): mniejszy rozmiar zapytania niz PNG; przykłady Google używaja image/jpeg.

    Zwraca (bytes, mime_type).
    """
    max_edge = _gemini_vision_max_edge()
    if max_edge is None:
        data = path.read_bytes()
        suf = path.suffix.lower()
        mime = "image/png" if suf == ".png" else "image/jpeg"
        return data, mime

    raw = path.read_bytes()
    im = _pil_to_rgb(Image.open(io.BytesIO(raw)))
    w, h = im.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        im = im.resize((nw, nh), resample)

    q_s = os.getenv("GEMINI_VISION_JPEG_QUALITY", "85").strip()
    try:
        quality = max(1, min(95, int(q_s)))
    except ValueError:
        quality = 85

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), "image/jpeg"


def parse_grid_gemini(path: Path, model: str) -> VisionBoardParse:
    """Google Generative Language API (Gemini) — obraz + tekst, bez OpenRouter."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Brak GEMINI_API_KEY w .env")
    img_bytes, img_mime = compress_image_for_gemini_context(path)
    b64 = base64.standard_b64encode(img_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    gen_cfg: dict[str, Any] = {
        "temperature": 0,
        # JSON 3x3 + brief: zwykle <1k tokenow wyjscia; nizszy limit = mniejsze obciazenie TPM.
        "maxOutputTokens": int(os.getenv("ELECTRICITY_VISION_MAX_OUTPUT", "2048")),
    }
    if _vision_wants_json_object_mode():
        gen_cfg["responseMimeType"] = "application/json"
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": VISION_SYSTEM}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": VISION_USER},
                    {
                        "inline_data": {
                            "mime_type": img_mime,
                            "data": b64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": gen_cfg,
    }
    max_retries = int(os.getenv("GEMINI_VISION_MAX_RETRIES", "4"))
    base_delay = float(os.getenv("GEMINI_VISION_RETRY_DELAY_SEC", "6"))
    r: requests.Response | None = None
    for attempt in range(max_retries + 1):
        r = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            json=body,
            timeout=120,
        )
        if r.status_code != 429:
            break
        if attempt >= max_retries:
            break
        ra = r.headers.get("Retry-After")
        try:
            sleep_s = float(ra) if ra else base_delay * (attempt + 1)
        except ValueError:
            sleep_s = base_delay * (attempt + 1)
        time.sleep(min(max(sleep_s, 1.0), 120.0))

    assert r is not None
    if r.status_code == 429:
        fb = os.getenv("ELECTRICITY_VISION_FALLBACK_OPENAI_ON_429", "1").strip().lower()
        if fb in ("1", "true", "yes", "on") and OPENAI_API_KEY:
            print(
                "[wizja] Gemini: 429 Too Many Requests — przejscie na OpenAI "
                f"({DEFAULT_OPENAI_MODEL}). Wylacz: ELECTRICITY_VISION_FALLBACK_OPENAI_ON_429=0",
                file=sys.stderr,
            )
            return parse_grid_openai(path, DEFAULT_OPENAI_MODEL)
        raise RuntimeError(
            "Gemini API zwrocilo 429 Too Many Requests — przekroczony limit zapytan "
            "(RPM/TPM/dzienny quota albo burst). "
            "Dodaj OPENAI_API_KEY (automatyczny fallback wizji) albo "
            "ELECTRICITY_VISION_PROVIDER=openai, albo poczekaj / zwieksz limit w Google AI Studio."
        )
    r.raise_for_status()
    resp = r.json()
    cands = resp.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini: brak candidates: {resp!r}")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text.strip():
        raise RuntimeError(f"Gemini: pusta odpowiedz: {resp!r}")
    data = _extract_json_object(text)
    return _parse_vision_full(data)


def parse_grid_openai(path: Path, model: str) -> VisionBoardParse:
    if not OPENAI_API_KEY:
        raise RuntimeError("Brak OPENAI_API_KEY")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "max_tokens": int(os.getenv("ELECTRICITY_OPENAI_VISION_MAX_TOKENS", "2048")),
        "messages": [
            {"role": "system", "content": VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_USER},
                    {
                        "type": "image_url",
                        "image_url": {"url": _png_data_url(path)},
                    },
                ],
            },
        ],
    }
    payload.update(_vision_response_format_block_openai())
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    data = _extract_json_object(str(content))
    return _parse_vision_full(data)


def parse_grid_vision(path: Path) -> VisionBoardParse:
    """Wizja: bezposrednio Gemini (GEMINI_API_KEY) lub OpenAI (OPENAI_API_KEY). Bez OpenRouter."""
    p = _vision_provider()
    if p == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("ELECTRICITY_VISION_PROVIDER=openai wymaga OPENAI_API_KEY")
        return parse_grid_openai(path, DEFAULT_OPENAI_MODEL)
    if p == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError("ELECTRICITY_VISION_PROVIDER=gemini wymaga GEMINI_API_KEY")
        return parse_grid_gemini(path, DEFAULT_GEMINI_VISION_MODEL)
    if GEMINI_API_KEY:
        return parse_grid_gemini(path, DEFAULT_GEMINI_VISION_MODEL)
    if OPENAI_API_KEY:
        return parse_grid_openai(path, DEFAULT_OPENAI_MODEL)
    raise RuntimeError("Brak GEMINI_API_KEY i OPENAI_API_KEY — uzyj --heuristic lub ustaw klucz.")


def log_vision_model_output(title: str, v: VisionBoardParse) -> None:
    """Logi konsoli: ten sam JSON co dostaje agent (komorka po komorce)."""
    print(f"\n=== {title} ===")
    print("[cells — JSON per pole: id, n,e,s,w, shape, brief]")
    for r in range(3):
        for c in range(3):
            cell = v.cells[r][c]
            line = json.dumps(cell, ensure_ascii=False)
            print(f"  {line}")
    print("")


def _luminance(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _rot_cw(pattern: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Jeden obrót 90° w prawo: (N,E,S,W) w układzie świata."""
    n, e, s, w = pattern
    return (w, n, e, s)


def _rotations_to_match(
    current: tuple[int, int, int, int], target: tuple[int, int, int, int]
) -> int | None:
    p = current
    for k in range(4):
        if p == target:
            return k
        p = _rot_cw(p)
    return None


def parse_cell_pattern(cell_rgb: np.ndarray, med_delta: float = 25.0) -> tuple[int, int, int, int]:
    """
    Zwraca (N,E,S,W) jako 0/1 — czy w środkowej części krawędzi jest „ciemny” kabel
    względem mediany jasności komórki.
    """
    h, w = cell_rgb.shape[0], cell_rgb.shape[1]
    L = _luminance(cell_rgb)
    med = float(np.median(L))
    wire = L < (med - med_delta)

    m = max(5, min(w, h) // 20)
    strip = m * 3
    cx0, cx1 = w // 4, 3 * w // 4
    cy0, cy1 = h // 4, 3 * h // 4

    def frac(mask: np.ndarray) -> float:
        return float(mask.mean()) if mask.size else 0.0

    top_m = wire[2 : 2 + strip, cx0:cx1]
    bot_m = wire[h - 2 - strip : h - 2, cx0:cx1]
    lef_m = wire[cy0:cy1, 2 : 2 + strip]
    rig_m = wire[cy0:cy1, w - 2 - strip : w - 2]

    thr = 0.12
    n = 1 if frac(top_m) > thr else 0
    e = 1 if frac(rig_m) > thr else 0
    s = 1 if frac(bot_m) > thr else 0
    w_ = 1 if frac(lef_m) > thr else 0
    return (n, e, s, w_)


def parse_grid(path: Path, med_delta: float) -> list[list[tuple[int, int, int, int]]]:
    im = Image.open(path).convert("RGB")
    arr = np.array(im)
    H, W = arr.shape[0], arr.shape[1]
    ch, cw = H // 3, W // 3
    grid: list[list[tuple[int, int, int, int]]] = []
    for r in range(3):
        row: list[tuple[int, int, int, int]] = []
        for c in range(3):
            y0, y1 = r * ch, (r + 1) * ch
            x0, x1 = c * cw, (c + 1) * cw
            row.append(parse_cell_pattern(arr[y0:y1, x0:x1], med_delta=med_delta))
        grid.append(row)
    return grid


def cell_name(r: int, c: int) -> str:
    return f"{r + 1}x{c + 1}"


def plan_rotations(
    current: list[list[tuple[int, int, int, int]]],
    target: list[list[tuple[int, int, int, int]]],
) -> list[tuple[str, int]] | None:
    """Lista (pole, liczba obrotów w prawo) lub None jeśli któraś komórka nie da się dopasować."""
    moves: list[tuple[str, int]] = []
    for r in range(3):
        for c in range(3):
            k = _rotations_to_match(current[r][c], target[r][c])
            if k is None:
                return None
            if k:
                moves.extend([(cell_name(r, c), 1)] * k)
    return moves


def self_check_target_parse(target: list[list[tuple[int, int, int, int]]]) -> bool:
    """Po parsowaniu wzorca docelowego samego z siebie — wszystkie k powinny być 0."""
    return plan_rotations(target, target) == []


def find_working_delta(solved_path: Path) -> float:
    """Wybiera med_delta tak, by schemat referencyjny był spójny (k=0 vs k=0)."""
    for d in (22.0, 25.0, 28.0, 30.0, 18.0, 32.0):
        g = parse_grid(solved_path, med_delta=d)
        if self_check_target_parse(g):
            return d
    return 25.0


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)


def electric_snap_path_factory() -> Callable[[], Path]:
    """Kolejne pliki electric_1.png, electric_2.png przy kazdym pobraniu planszy z huba."""
    n = [0]

    def next_path() -> Path:
        n[0] += 1
        return BASE_DIR / f"electric_{n[0]}.png"

    return next_path


def verify_rotate(field: str) -> dict:
    if not HUB_API_KEY:
        raise RuntimeError("Brak HUB_API_KEY w .env")
    body = {
        "apikey": HUB_API_KEY,
        "task": "electricity",
        "answer": {"rotate": field},
    }
    resp = requests.post(VERIFY_URL, json=body, timeout=60)
    resp.raise_for_status()
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"raw": resp.text}


AGENT_SYSTEM = """Jestes agentem rozwiazujacym zadanie electricity na hubie (plansza 3x3).
Zasady:
- Adres pola: AxB — wiersz A i kolumna B (1-3), np. 3x1 to lewy dolny rog.
- Jedyna operacja: obrot pola o 90 stopni w PRAWO; kazdy obrot = jedno wywolanie narzedzia rotate_cell.
- Cel: uklad kabli ma odpowiadac schematowi docelowemu (get_target_schema). Zrodlo w lewy dolny rog; obwod zamkniety (jak w task.md).
- ZAWSZE opieraj sie na polu "comparison" z odpowiedzi get_current_board (gdy jest): tam jest kazda komorka, target vs current, rotations_needed_cw_90 (0-3 lub null).
- Jesli match_complete=true albo wszystkie komorki maja rotations_needed_cw_90=0: uklad ZGODNY Z CELEM — NIE wywoluj rotate_cell (obrocenie zepsuje uklad). Oczekuj FLG w odpowiedzi z huba lub ponownie get_current_board jesli wizja byla chybiona.
- Obracaj TYLKO komorki z rotations_needed_cw_90 > 0, dokladnie tyle razy ile wynika (k razy rotate_cell na to samo pole).
- Jesli impossible / IMPOSSIBLE_TILE_TYPE: obrot nie pomoze — reset_board lub ponowny odczyt wizji.
- Jesli rotate_cell zwroci FLG — koncz.
- Po kazdej serii obrotow: get_current_board i porownaj z celem (comparison).
- W odpowiedzi narzedzi pole cells zawiera ten sam JSON co wizja (id, n,e,s,w, shape, brief) — pomocniczo; nadrzedne jest comparison."""


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_target_schema",
            "description": (
                "Pobiera solved_electricity.png; model wizyjny zwraca cells (3x3: id, n,e,s,w, shape, brief). "
                "Wywolaj na poczatku."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_board",
            "description": (
                "Pobiera swiezy PNG planszy z huba; zapisuje jako electric_1.png, electric_2.png, ...; zwraca cells (jak wyzej) oraz comparison wzgledem celu."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rotate_cell",
            "description": "Wysyla do huba jeden obrot 90 w prawo dla podanego pola.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": 'Pole w formacie "AxB", np. "2x3"',
                    }
                },
                "required": ["field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_board",
            "description": "Resetuje plansze (GET electricity.png?reset=1). Opcjonalnie gdy stan jest zly.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _get_agent_client() -> tuple[OpenAI, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("Agent wymaga OPENAI_API_KEY (bezposrednio api.openai.com, bez OpenRouter).")
    return OpenAI(api_key=OPENAI_API_KEY), DEFAULT_AGENT_MODEL


def run_agent(
    *,
    reset: bool,
    dry_run: bool,
    max_rounds: int = 48,
) -> int:
    if not HUB_API_KEY:
        print("Ustaw HUB_API_KEY w .env", file=sys.stderr)
        return 1
    if not OPENAI_API_KEY:
        print("Agent wymaga OPENAI_API_KEY (model tekstowy + function calling).", file=sys.stderr)
        return 1

    solved_path = BASE_DIR / "solved_electricity.png"
    key = HUB_API_KEY
    current_url = f"https://hub.ag3nts.org/data/{key}/electricity.png"
    reset_url = f"https://hub.ag3nts.org/data/{key}/electricity.png?reset=1"
    next_electric_path = electric_snap_path_factory()

    cached_target: list[list[tuple[int, int, int, int]]] | None = None

    def tool_get_target_schema() -> dict[str, Any]:
        nonlocal cached_target
        print("[narzedzie] get_target_schema (wizja: tylko odczyt PNG docelowego)")
        download(SOLVED_PNG_URL, solved_path)
        vp = parse_grid_vision(solved_path)
        target_grid = vp.grid
        cached_target = target_grid
        log_vision_model_output("CEL — model wizyjny opisuje solved_electricity.png", vp)
        print("=== CEL — siatka N/E/S/W (wizja) ===")
        print(format_grid_with_row_labels(target_grid))
        print("")
        return {
            "cells": vp.cells,
            "grid": _grid_as_dicts(target_grid),
            "ascii": format_grid_ascii(target_grid),
            "labeled_rows": format_grid_with_row_labels(target_grid),
            "note": "Pole cells jest kanonicznym wynikiem wizji (to samo co w logu). get_current_board dodaje comparison.",
        }

    def tool_get_current_board() -> dict[str, Any]:
        print("[narzedzie] get_current_board (wizja: tylko odczyt PNG biezacego)")
        dest = next_electric_path()
        download(current_url, dest)
        vp = parse_grid_vision(dest)
        g = vp.grid
        out: dict[str, Any] = {
            "cells": vp.cells,
            "grid": _grid_as_dicts(g),
            "ascii": format_grid_ascii(g),
            "labeled_rows": format_grid_with_row_labels(g),
        }
        log_vision_model_output(f"AKTUALNY stan — model wizyjny opisuje {dest.name}", vp)
        if cached_target is None:
            out["warning"] = "Brak celu w pamieci — najpierw get_target_schema."
            print("=== AKTUALNY — siatka N/E/S/W (wizja) — brak celu do porownania ===")
            print(format_grid_with_row_labels(g))
            print("")
            return out
        cmp = compare_grids_for_agent(g, cached_target)
        out["comparison"] = cmp
        out["match_complete"] = cmp["match_complete"]
        print_vision_dual_and_summary(
            g, cached_target, header="Wizja: aktualny vs cel", cmp=cmp
        )
        print("")
        return out

    def tool_rotate_cell(field: str) -> dict[str, Any]:
        print(f"[narzedzie] rotate_cell({field})")
        field = field.strip()
        if not re.fullmatch(r"[1-3]x[1-3]", field):
            return {"error": 'Pole musi byc w formacie "AxB" z A,B w 1..3, np. "2x3".', "got": field}
        if dry_run:
            return {"dry_run": True, "field": field, "message": "pominieto POST (--dry-run)"}
        return verify_rotate(field)

    def tool_reset_board() -> dict[str, Any]:
        print("[narzedzie] reset_board")
        dest = next_electric_path()
        download(reset_url, dest)
        return {
            "ok": True,
            "saved_as": dest.name,
            "message": f"Pobrano PNG po resecie ({dest.name}); uzyj get_current_board.",
        }

    def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_target_schema":
            return tool_get_target_schema()
        if name == "get_current_board":
            return tool_get_current_board()
        if name == "rotate_cell":
            return tool_rotate_cell(str(args.get("field", "")).strip())
        if name == "reset_board":
            return tool_reset_board()
        return {"error": f"nieznane narzedzie: {name}"}

    if reset:
        tool_reset_board()

    client, model = _get_agent_client()
    print(f"Agent (tekst): {model} | wizja: {_active_vision_label()}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {
            "role": "user",
            "content": (
                "Rozwiaz puzzle electricity. Kolejnosc: get_target_schema, get_current_board. "
                "Oba narzedzia zwracaja cells: 3x3 tablica obiektow (id, n,e,s,w, shape, brief) — ten sam format "
                "co model wizyjny. Do ruchow uzyj comparison.rotations_needed_cw_90. "
                "Gdy match_complete=true — zero obrotow. Po obrotach znow get_current_board."
            ),
        },
    ]

    for _ in range(max_rounds):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=AGENT_TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        tcalls = getattr(msg, "tool_calls", None) or []
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content,
        }
        if tcalls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in tcalls
            ]
        messages.append(assistant_msg)

        if not tcalls:
            text = (msg.content or "").strip()
            print(f"[agent] {text}")
            if "FLG" in text:
                return 0
            messages.append(
                {
                    "role": "user",
                    "content": "Kontynuuj: wywolaj narzedzia aby doprowadzic plansze do celu lub zakoncz gdy masz flage.",
                }
            )
            continue

        nudges: list[str] = []
        for tc in tcalls:
            name = tc.function.name
            try:
                raw_args = tc.function.arguments or "{}"
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            result = dispatch(name, args)
            result_str = json.dumps(result, ensure_ascii=False)
            if "FLG" in result_str:
                print(result_str)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                }
            )
            if (
                name == "get_current_board"
                and isinstance(result, dict)
                and result.get("match_complete")
            ):
                nudges.append(
                    "System: match_complete=true — wizja uznaje uklad za zgodny z celem. "
                    "NIE wywoluj rotate_cell. Jesli nie ma jeszcze FLG w odpowiedziach verify, "
                    "odczyt wizji mogl sie pomylic; ponow get_current_board lub reset_board."
                )
            if not dry_run and isinstance(result, dict):
                msg_txt = json.dumps(result, ensure_ascii=False)
                if "FLG" in msg_txt:
                    print("Otrzymano flage z huba.")
                    return 0

        if nudges:
            messages.append({"role": "user", "content": nudges[0]})

    print("Przekroczono limit rund agenta.", file=sys.stderr)
    return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="electricity — hub 3x3")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="jednorazowy plan obrotow bez agenta (stary tryb)",
    )
    parser.add_argument("--reset", action="store_true", help="GET electricity.png?reset=1 przed gra")
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="(tylko --legacy) parsowanie PNG przez progi jasnosci",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="bez POST rotate do huba (agent: narzedzie rotate zwraca dry-run)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=48,
        help="maks. iteracji petli agenta (domyslnie 48)",
    )
    args = parser.parse_args()

    if not HUB_API_KEY:
        print("Ustaw HUB_API_KEY w .env", file=sys.stderr)
        return 1

    if not args.legacy:
        return run_agent(reset=args.reset, dry_run=args.dry_run, max_rounds=args.max_rounds)

    use_vision = not args.heuristic and (GEMINI_API_KEY or OPENAI_API_KEY)
    if not use_vision and not args.heuristic:
        print(
            "Brak GEMINI_API_KEY / OPENAI_API_KEY — uzywam heurystyki. "
            "Dodaj klucz lub uruchom z --heuristic jawnie.",
            file=sys.stderr,
        )
        use_vision = False

    solved_path = BASE_DIR / "solved_electricity.png"
    key = HUB_API_KEY
    current_url = f"https://hub.ag3nts.org/data/{key}/electricity.png"
    reset_url = f"https://hub.ag3nts.org/data/{key}/electricity.png?reset=1"
    next_electric_path = electric_snap_path_factory()

    print("Pobieranie wzorca docelowego...")
    download(SOLVED_PNG_URL, solved_path)

    if args.reset:
        print("Reset planszy...")
        current_path = next_electric_path()
        download(reset_url, current_path)
    else:
        print("Pobieranie aktualnego stanu...")
        current_path = next_electric_path()
        download(current_url, current_path)

    if use_vision:
        print(f"Analiza obrazow modelem wizji: {_active_vision_label()}")
        vp_target = parse_grid_vision(solved_path)
        vp_current = parse_grid_vision(current_path)
        log_vision_model_output("LEGACY — cel (solved_electricity.png)", vp_target)
        log_vision_model_output(f"LEGACY — aktualny stan ({current_path.name})", vp_current)
        target = vp_target.grid
        current = vp_current.grid
    else:
        med_delta = find_working_delta(solved_path)
        print(f"Heurystyka: mediana jasnosci komorki minus delta (delta={med_delta})")
        target = parse_grid(solved_path, med_delta=med_delta)
        current = parse_grid(current_path, med_delta=med_delta)

    print("Aktualny stan (N/E/S/W):")
    print(format_grid_ascii(current))
    print("Cel:")
    print(format_grid_ascii(target))

    moves = plan_rotations(current, target)
    if moves is None:
        print(
            "Nie udalo sie dopasowac ktorejs komorki obrotami (np. blad odczytu obrazu). "
            "Sprobuj --reset, innego modelu wizji, lub trybu agenta (bez --legacy).",
            file=sys.stderr,
        )
        return 2

    print(f"Plan: {len(moves)} obrotów (łącznie)")
    for field, _ in moves:
        print(f"  -> {field}")

    if args.dry_run:
        return 0

    last: dict = {}
    for field, _ in moves:
        last = verify_rotate(field)
        txt = json.dumps(last, ensure_ascii=False)
        print(txt)
        if "FLG" in txt or (isinstance(last, dict) and "FLG" in str(last.get("message", ""))):
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
