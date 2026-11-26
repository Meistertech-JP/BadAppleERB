"""Decode the actual terminal character state, including Japanese wide cells.

This records logical cells and paints a representative font preview with
explicitly selected ASCII and Japanese fonts.
"""
from __future__ import annotations
import hashlib
import re
import unicodedata
from pathlib import Path
import numpy as np

CSI = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")


class MenuScreen:
    def __init__(self):
        self.char = np.full((25, 80), " ", dtype=object)
        self.fg_cells = np.full((25, 80, 3), 255, dtype=np.uint8)
        self.bg_cells = np.zeros((25, 80, 3), dtype=np.uint8)
        self.fg, self.bg = (255, 255, 255), (0, 0, 0)
        self.x = self.y = 0
        self.active = False
        self.pending = ""
        self.unsupported = []
        self.overflows = []
        self.scrolls = 0
        self.frames = []

    def clear(self, y, x0=0, x1=80):
        self.char[y, x0:x1] = " "
        self.fg_cells[y, x0:x1] = self.fg
        self.bg_cells[y, x0:x1] = self.bg

    def image_snapshot(self):
        chars = self.char[:24, :79]
        if np.any((chars != "#") & (chars != " ")):
            return
        rgb = np.where((chars == "#")[:, :, None], self.fg_cells[:24, :79], self.bg_cells[:24, :79])
        if np.any(rgb[:, :, 0] != rgb[:, :, 1]) or np.any(rgb[:, :, 0] != rgb[:, :, 2]):
            return
        gray = rgb[:, :, 0].copy()
        key = hashlib.sha256(gray.tobytes()).hexdigest()
        if not self.frames or self.frames[-1][0] != key:
            self.frames.append((key, gray))

    def control(self, params, command):
        private = params.startswith("?")
        values = [int(v) if v else 0 for v in params.lstrip("?").split(";")]
        if private and command in ("h", "l"):
            if values == [1049]:
                self.active = command == "h"
                if self.active:
                    self.char[:] = " "
                    self.bg_cells[:] = 0
                    self.fg_cells[:] = 255
                    self.x = self.y = 0
            elif values not in ([25], [7], [2004]):
                self.unsupported.append(f"CSI {params}{command}")
        elif command in ("H", "f"):
            self.y = (values[0] or 1) - 1
            self.x = (values[1] or 1) - 1 if len(values) > 1 else 0
            if self.active and (self.y, self.x) == (24, 0):
                self.image_snapshot()
        elif command == "K":
            if 0 <= self.y < 25:
                mode = values[0]
                self.clear(self.y, self.x if mode == 0 else 0, self.x + 1 if mode == 1 else 80)
        elif command == "J":
            mode = values[0]
            if mode == 2:
                for y in range(25):
                    self.clear(y)
            elif mode == 0:
                if 0 <= self.y < 25:
                    self.clear(self.y, self.x)
                for y in range(max(0, self.y + 1), 25):
                    self.clear(y)
            else:
                self.unsupported.append(f"CSI {params}J")
        elif command == "m":
            i = 0
            while i < len(values):
                n = values[i]
                if n == 0:
                    self.fg, self.bg = (255, 255, 255), (0, 0, 0)
                elif n == 39:
                    self.fg = (255, 255, 255)
                elif n == 49:
                    self.bg = (0, 0, 0)
                elif n in (38, 48) and i + 4 < len(values) and values[i + 1] == 2:
                    color = tuple(values[i + 2:i + 5])
                    if n == 38:
                        self.fg = color
                    else:
                        self.bg = color
                    i += 4
                elif n not in (1, 2, 3, 4, 22, 23, 24):
                    self.unsupported.append(f"SGR {n}")
                i += 1
        elif command in ("A", "B", "C", "D"):
            n = values[0] or 1
            if command == "A": self.y = max(0, self.y - n)
            elif command == "B": self.y = min(24, self.y + n)
            elif command == "C": self.x = min(79, self.x + n)
            else: self.x = max(0, self.x - n)
        else:
            self.unsupported.append(f"CSI {params}{command}")

    def feed(self, new_text):
        text = self.pending + new_text
        self.pending = ""
        i = 0
        while i < len(text):
            if text[i] == "\x1b":
                match = CSI.match(text, i)
                if not match:
                    if text[i:] == "\x1b" or text[i:].startswith("\x1b["):
                        self.pending = text[i:]
                        break
                    self.unsupported.append(repr(text[i:i + 16]))
                    i += 1
                    continue
                self.control(match.group(1), match.group(3))
                i = match.end()
                continue
            char = text[i]
            i += 1
            if char == "\r":
                self.x = 0
                continue
            if char == "\n":
                self.y += 1
                if self.y >= 25:
                    self.char[:-1] = self.char[1:]
                    self.fg_cells[:-1] = self.fg_cells[1:]
                    self.bg_cells[:-1] = self.bg_cells[1:]
                    self.y = 24
                    self.clear(24)
                    self.scrolls += 1
                continue
            if char == "\b":
                self.x = max(0, self.x - 1)
                continue
            if ord(char) < 32:
                continue
            if unicodedata.combining(char):
                if self.x:
                    self.char[self.y, self.x - 1] += char
                continue
            width = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if self.x + width > 80:
                self.overflows.append({"row": self.y, "column": self.x, "character": char})
                self.x = 0
                self.y += 1
            if 0 <= self.y < 25:
                self.char[self.y, self.x] = char
                self.fg_cells[self.y, self.x:self.x + width] = self.fg
                self.bg_cells[self.y, self.x:self.x + width] = self.bg
                if width == 2:
                    self.char[self.y, self.x + 1] = ""
            else:
                self.overflows.append({"row": self.y, "column": self.x, "character": char})
            self.x += width

    def lines(self):
        return ["".join(row) for row in self.char.tolist()]

    def state(self):
        occupied = np.argwhere((self.char != " ") & (self.char != ""))
        # Include continuation cells in extent, rather than counting only CJK heads.
        occupied_all = np.argwhere(self.char != " ")
        return {
            "terminal": [80, 25], "cursor": [self.x, self.y], "active_alternate_screen": self.active,
            "lines": self.lines(), "characters": self.char.tolist(),
            "foreground_rgb": self.fg_cells.tolist(), "background_rgb": self.bg_cells.tolist(),
            "max_nonblank_row": int(occupied_all[:, 0].max()) + 1 if len(occupied_all) else 0,
            "max_nonblank_column": int(occupied_all[:, 1].max()) + 1 if len(occupied_all) else 0,
            "last_row_blank": not bool(np.any(self.char[24] != " ")),
            "last_column_blank": not bool(np.any(self.char[:, 79] != " ")),
            "unsupported_ansi": list(self.unsupported), "physical_overflow_events": list(self.overflows),
            "preview_scope": "Captured terminal character/color state rendered with fixed fonts",
        }


def render_state(state: dict, output: Path, *, ascii_font_path: Path | None = None,
                 cjk_font_path: Path | None = None) -> None:
    from PIL import Image, ImageDraw, ImageFont
    ascii_path = ascii_font_path or Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    cjk_path = cjk_font_path or Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    try:
        ascii_font = ImageFont.truetype(str(ascii_path), 20)
        cjk_font = ImageFont.truetype(str(cjk_path), 22)
    except OSError as exc:
        raise RuntimeError(
            "Menu preview requires a monospaced ASCII font and a Japanese CJK font. "
            "Install DejaVu Sans Mono and Noto Sans CJK, or supply --ascii-font and "
            f"--cjk-font. Requested font files: {ascii_path}, {cjk_path}"
        ) from exc
    cw, ch = 12, 25
    image = Image.new("RGB", (80 * cw, 25 * ch))
    draw = ImageDraw.Draw(image)
    for y in range(25):
        for x in range(80):
            bg = tuple(state["background_rgb"][y][x])
            draw.rectangle((x*cw, y*ch, (x+1)*cw-1, (y+1)*ch-1), fill=bg)
    for y, row in enumerate(state["characters"]):
        for x, char in enumerate(row):
            if not char or char == " ":
                continue
            font = cjk_font if ord(char[0]) > 127 else ascii_font
            draw.text((x*cw, y*ch+21), char, font=font, fill=tuple(state["foreground_rgb"][y][x]), anchor="ls")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
