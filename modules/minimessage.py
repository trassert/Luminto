"""
minimessage.py — рендерер MiniMessage (Adventure) в PNG.
Вход:  строка MiniMessage, напр. "<gradient:#54daf4:#545eb6>Birdflop</gradient>"
Выход: PNG-картинка в стиле Minecraft (шрифт fonts/minecraft.ttf, тень, декорации).
Поддерживается:
    • цвета: <red>, <dark_aqua>, ..., <white>, <#RRGGBB>, <color:#RRGGBB>, <colour:red>
    • декорации: <bold>, <italic>, <underlined>/<underline>, <strikethrough>,
        <obfuscated>/<obf>, выключение через <bold:false> или <!bold>
    • <gradient:c1:c2:...> (любое число цветов, фаза: <gradient:0.5:red:blue>)
    • <rainbow>, <rainbow:2>, <rainbow:2:0.5> (Плотность и фаза)
    • <reset>, <newline>, <font:name> (маппинг имён через --map-font)
    • Экранирование
click/hover/insertion/lang/translatable/key/keybind/score/selector/nbt/shadow
    не рендерятся (в картинке не имеют смысла), но их содержимое сохраняется,
    неизвестные теги выводятся как обычный текст.
"""

from __future__ import annotations

import colorsys
import math
import random
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from . import pathes

logger.info(f"Загружен модуль {__name__}")


MAGIC_CHARS = string.ascii_letters + string.digits + "!@#$%&*()?/=+~"
NAMED_COLORS = {
    "black": "000000",
    "dark_blue": "0000AA",
    "dark_green": "00AA00",
    "dark_aqua": "00AAAA",
    "dark_red": "AA0000",
    "dark_purple": "AA00AA",
    "gold": "FFAA00",
    "gray": "AAAAAA",
    "dark_gray": "555555",
    "blue": "5555FF",
    "green": "55FF55",
    "aqua": "55FFFF",
    "red": "FF5555",
    "light_purple": "FF55FF",
    "yellow": "FFFF55",
    "white": "FFFFFF",
}
COLOR_ALIASES = {"grey": "gray", "dark_grey": "dark_gray"}
DECORATIONS = {
    "bold": "bold",
    "italic": "italic",
    "underlined": "underlined",
    "underline": "underlined",
    "strikethrough": "strikethrough",
    "strike": "strikethrough",
    "st": "strikethrough",
    "obfuscated": "obfuscated",
    "obf": "obfuscated",
    "magic": "obfuscated",
}
VOID_TAGS = {
    "click",
    "hover",
    "insertion",
    "font_meta",
    "lang",
    "translatable",
    "translate",
    "key",
    "keybind",
    "score",
    "selector",
    "nbt",
    "shadow",
}
STRICT_TAG_RE = re.compile(r"[A-Za-z0-9_:#.\-/!]+")
HEX_RE = re.compile(r"(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_FLOATS = {"nan", "inf", "-inf", "+inf", "infinity", "-infinity"}


@dataclass
class Node:
    kind: str
    keys: tuple = ()
    payload: object = None
    children: list = field(default_factory=list)
    text: str = ""


def parse_color_spec(spec: str):
    s = spec.strip().lower()
    if s.startswith("#"):
        h = s[1:]
        if HEX_RE.match(h):
            if len(h) == 3:
                h = "".join(ch * 2 for ch in h)
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        return None
    s = COLOR_ALIASES.get(s, s)
    if s in NAMED_COLORS:
        h = NAMED_COLORS[s]
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return None


def _is_float(tok: str) -> bool:
    if tok.lower() in _FLOATS:
        return False
    try:
        float(tok)
    except ValueError:
        return False
    else:
        return True


def parse_gradient_args(args):
    """[фаза] цвет1:цвет2:... -> (colors, phase) или None."""
    phase, i = 0.0, 0
    if args and _is_float(args[0]):
        phase, i = float(args[0]), 1
    colors = []
    for a in args[i:]:
        rgb = parse_color_spec(a)
        if rgb is None:
            return None
        colors.append(rgb)
    if len(colors) < 2:
        return None
    return colors, phase


def parse_rainbow_args(args):
    density, phase = 1.0, 0.0
    if args:
        if not _is_float(args[0]):
            return None
        density = float(args[0])
    if len(args) > 1:
        if not _is_float(args[1]):
            return None
        phase = float(args[1])
    return density, phase


def tokenize(s: str):
    """Разбивает строку на text/open/close токены с учётом экранирования \\< и \\\\."""
    toks, buf, i, n = [], [], 0, len(s)

    def flush():
        if buf:
            toks.append(("text", "".join(buf)))
            buf.clear()

    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n and s[i + 1] in "<\\":
            buf.append(s[i + 1])
            i += 2
            continue
        if c == "<":
            j = s.find(">", i + 1)
            if j != -1 and "\n" not in s[i + 1 : j]:
                tok = parse_tag_body(s[i + 1 : j])
                if tok:
                    flush()
                    toks.append(tok)
                    i = j + 1
                    continue
        buf.append(c)
        i += 1
    flush()
    return toks


def parse_tag_body(body: str):
    if not body:
        return None
    closing = body.startswith("/")
    rest = body[1:] if closing else body
    if not rest:
        return None
    base = rest.split(":", 1)[0].lower().lstrip("!")
    if base in VOID_TAGS:
        pass
    elif not STRICT_TAG_RE.fullmatch(rest):
        return None
    name = rest.split(":", 1)[0].lower()
    args = rest.split(":")[1:] if ":" in rest else []
    if closing:
        return ("close", name)
    return ("open", name, args, body)


def make_node(name: str, args: list):
    """Возвращает Node для открывающего тега или None (неизвестный тег -> текст)."""
    neg = name.startswith("!")
    n = name[1:] if neg else name
    if n.startswith("#"):
        rgb = parse_color_spec(n)
        return Node("color", keys=(n, "color"), payload=rgb) if rgb else None
    if n in COLOR_ALIASES or n in NAMED_COLORS:
        return Node("color", keys=(n,), payload=parse_color_spec(n))
    if n in ("color", "colour"):
        if not args:
            return None
        rgb = parse_color_spec(args[0])
        if rgb is None:
            return None
        return Node("color", keys=(n, f"{n}:{args[0].lower()}"), payload=rgb)
    if n in DECORATIONS:
        canon = DECORATIONS[n]
        on = not neg
        if args:
            a = args[0].lower()
            if a in ("false", "0", "off"):
                on = False
            elif a in ("true", "1", "on"):
                on = True
            else:
                return None
        return Node("deco", keys=(name, canon), payload=(canon, on))
    if n == "gradient":
        parsed = parse_gradient_args(args)
        if parsed is None:
            return None
        return Node("gradient", keys=("gradient",), payload=parsed)
    if n == "rainbow":
        parsed = parse_rainbow_args(args)
        if parsed is None:
            return None
        return Node("rainbow", keys=("rainbow",), payload=parsed)
    if n == "reset":
        return Node("reset", keys=("reset",))
    if n in ("newline", "br"):
        return Node("text", text="\n")
    if n == "font":
        return Node("font", keys=("font",), payload=":".join(args))
    if n in VOID_TAGS:
        return Node("noop", keys=(n,))
    return None


def build_tree(tokens) -> Node:
    root = Node("root")
    stack = [root]
    for tok in tokens:
        cur = stack[-1]
        if tok[0] == "text":
            cur.children.append(Node("text", text=tok[1]))
        elif tok[0] == "close":
            name = tok[1]
            idx = None
            for k in range(len(stack) - 1, 0, -1):
                if name in stack[k].keys:
                    idx = k
                    break
            if idx is None:
                cur.children.append(Node("text", text=f"</{name}>"))
            else:
                del stack[idx:]
        else:
            _, name, args, raw = tok
            node = make_node(name, args)
            if node is None:
                cur.children.append(Node("text", text=f"<{raw}>"))
            else:
                cur.children.append(node)
                if node.kind != "text":
                    stack.append(node)
    return root


def parse_minimessage(text: str) -> Node:
    return build_tree(tokenize(text))


class GradientPainter:
    def __init__(self, colors, phase, n):
        self.colors, self.phase, self.n, self.i = colors, phase, n, 0

    def next(self):
        i, self.i = self.i, self.i + 1
        t = 0.0 if self.n <= 1 else i / (self.n - 1)
        t = min(1.0, max(0.0, t + self.phase))
        k = len(self.colors) - 1
        p = t * k
        seg = min(int(p), k - 1)
        u = p - seg
        c0, c1 = self.colors[seg], self.colors[seg + 1]
        return tuple(round(c0[j] + (c1[j] - c0[j]) * u) for j in range(3))


class RainbowPainter:
    def __init__(self, density, phase, n):
        self.density, self.phase, self.n, self.i = density, phase, max(1, n), 0

    def next(self):
        i, self.i = self.i, self.i + 1
        hue = (self.phase + i * self.density / self.n) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return round(r * 255), round(g * 255), round(b * 255)


@dataclass
class Ctx:
    painter: object = None
    deco: frozenset = frozenset()
    font: str = "minecraft"


def visible_len(node: Node) -> int:
    if node.kind == "text":
        return sum(1 for c in node.text if c != "\n")
    return sum(visible_len(c) for c in node.children)


def flatten(node: Node, ctx: Ctx, out: list):
    k = node.kind
    if k in ("root", "noop"):
        for c in node.children:
            flatten(c, ctx, out)
    elif k == "text":
        for ch in node.text:
            if ch == "\n":
                out.append(None)
                continue
            p = ctx.painter
            if p is None:
                color = (255, 255, 255)
            elif isinstance(p, tuple):
                color = p[1]
            else:
                color = p.next()
            disp = ch
            if "obfuscated" in ctx.deco and not ch.isspace():
                disp = random.choice(MAGIC_CHARS)
            out.append(
                {
                    "ch": disp,
                    "ref": ch,
                    "color": color,
                    "deco": ctx.deco,
                    "font": ctx.font,
                }
            )
    elif k == "color":
        c2 = Ctx(("color", node.payload), ctx.deco, ctx.font)
        for c in node.children:
            flatten(c, c2, out)
    elif k == "gradient":
        colors, phase = node.payload
        c2 = Ctx(
            GradientPainter(colors, phase, visible_len(node)),
            ctx.deco,
            ctx.font,
        )
        for c in node.children:
            flatten(c, c2, out)
    elif k == "rainbow":
        density, phase = node.payload
        c2 = Ctx(
            RainbowPainter(density, phase, visible_len(node)),
            ctx.deco,
            ctx.font,
        )
        for c in node.children:
            flatten(c, c2, out)
    elif k == "deco":
        name, on = node.payload
        s = set(ctx.deco)
        (s.add if on else s.discard)(name)
        c2 = Ctx(ctx.painter, frozenset(s), ctx.font)
        for c in node.children:
            flatten(c, c2, out)
    elif k == "reset":
        c2 = Ctx(None, frozenset(), "minecraft")
        for c in node.children:
            flatten(c, c2, out)
    elif k == "font":
        c2 = Ctx(ctx.painter, ctx.deco, node.payload or "minecraft")
        for c in node.children:
            flatten(c, c2, out)


class FontBank:
    def __init__(self, default_path: Path, scale: int, extra: dict):
        self.size = max(8, 8 * scale)
        self.scale = max(1, self.size // 8)
        self.extra = extra
        self.cache = {}
        self.default_font = self._load(str(default_path))

    def _load(self, path: str):
        return ImageFont.truetype(path, self.size)

    def get(self, name: str):
        if name in self.cache:
            return self.cache[name]
        path = self.extra.get(name)
        f = self._load(path) if path else self.default_font
        self.cache[name] = f
        return f


class Renderer:
    ITALIC_K = 0.25

    def __init__(self, bank, shadow=True, bg=(38, 38, 38), bg_image=None):
        self.bank, self.shadow, self.bg, self.bg_image = (
            bank,
            shadow,
            bg,
            bg_image,
        )
        self.metrics = {}

    def metric(self, font):
        try:
            return self.metrics[font]
        except KeyError:
            ascent, descent = font.getmetrics()
            self.metrics[font] = (ascent, descent)
            return ascent, descent

    def char_advance(self, font, ch):
        try:
            return font.getlength(ch)
        except AttributeError:
            return font.getsize(ch)[0]

    def render(self, flat: list) -> Image.Image:
        bank = self.bank
        s = bank.scale
        pad = 2 * s
        lines = [[]]
        for item in flat:
            if item is None:
                lines.append([])
            else:
                lines[-1].append(item)
        widths = []
        for line in lines:
            w = 0.0
            for it in line:
                font = bank.get(it["font"])
                w += self.char_advance(font, it["ref"])
            widths.append(w)
        max_w = math.ceil(max(widths)) if widths else 0
        d_asc, d_desc = self.metric(bank.default_font)
        line_h = d_asc + d_desc
        spacing = s
        line_adv = line_h + spacing
        W = max(1, max_w + 2 * pad + s)
        H = max(1, len(lines) * line_adv - spacing + 2 * pad)
        if self.bg_image is not None:
            base = self.bg + (255,) if self.bg else (0, 0, 0, 0)
            img = Image.new("RGBA", (W, H), base)
            bw, bh = self.bg_image.size
            img.alpha_composite(
                self.bg_image.convert("RGBA"), ((W - bw) // 2, (H - bh) // 2)
            )
        else:
            img = Image.new(
                "RGBA", (W, H), self.bg + (255,) if self.bg else (0, 0, 0, 0)
            )
        dr = ImageDraw.Draw(img)
        for li, line in enumerate(lines):
            baseline = pad + li * line_adv + d_asc
            chars = []
            x = float(pad)
            for it in line:
                font = bank.get(it["font"])
                adv = self.char_advance(font, it["ref"])
                chars.append((it, font, adv, x))
                x += adv
            if self.shadow:
                self._pass(img, dr, chars, baseline, s, shadow=True)
            self._pass(img, dr, chars, baseline, s, shadow=False)
        return img

    def _pass(self, img, dr, chars, baseline, s, shadow):
        for it, font, adv, x in chars:
            ch = it["ref"]
            if ch.isspace():
                continue
            color = (
                it["color"]
                if not shadow
                else tuple(c // 4 for c in it["color"])
            )
            bold = "bold" in it["deco"]
            italic = "italic" in it["deco"]
            dx = s if shadow else 0
            self._blit(
                img,
                font,
                it["ch"],
                color,
                bold,
                italic,
                round(x) + dx,
                baseline + dx,
                s,
            )
        for it, font, adv, x in chars:
            asc, _ = self.metric(font)
            color = (
                it["color"]
                if not shadow
                else tuple(c // 4 for c in it["color"])
            )
            dx = s if shadow else 0
            if "underlined" in it["deco"]:
                dr.rectangle(
                    [
                        round(x) + dx,
                        baseline + dx,
                        round(x + adv) + dx + s - 1,
                        baseline + dx + s - 1,
                    ],
                    fill=color + (255,),
                )
            if "strikethrough" in it["deco"]:
                y0 = baseline - math.ceil(asc * 0.5)
                dr.rectangle(
                    [
                        round(x) + dx,
                        y0 + dx,
                        round(x + adv) + dx + s - 1,
                        y0 + dx + s - 1,
                    ],
                    fill=color + (255,),
                )

    def _blit(self, img, font, ch, color, bold, italic, x, baseline, s):
        asc, desc = self.metric(font)
        adv = self.char_advance(font, ch)
        h = asc + desc
        m = math.ceil(self.ITALIC_K * h) + s + 1
        w = math.ceil(adv) + 2 * m + s
        tile = Image.new("RGBA", (w, h + 2 * m), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        fill = color + (255,)
        d.text((m, m), ch, font=font, fill=fill)
        if bold:
            d.text((m + s, m), ch, font=font, fill=fill)
        if italic:
            tile = tile.transform(
                tile.size, Image.AFFINE, (1, self.ITALIC_K, 0, 0, 1, 0)
            )
        a = tile.getchannel("A").point(lambda v: 255 if v >= 120 else 0)
        tile.putalpha(a)
        img.alpha_composite(tile, (x - m, baseline - asc - m))


def render(
    text: str,
    out_path: Path,
    font_path: Path = pathes.font,
    scale: int = 6,
    shadow: bool = True,
    bg: (int, int, int) = (38, 38, 38),
    bg_image: Path = pathes.mini_pic_bg,
    extra_fonts=None,
    max_len: int = 32,
):
    """
    Рендерит MiniMessage в PNG.

    text: строка MiniMessage (str)
    font_path: путь к шрифту (Path, TTF)
    scale: масштаб (int, 1..n)
    shadow: рисовать тень (bool, True/False)
    bg: цвет фона (tuple, RGB)
    bg_image: путь к картинке фона (Path, PNG/JPG)
    extra_fonts: словарь {имя шрифта: путь к TTF} для <font:name> (dict)
    out_path: путь к выходной картинке (Path, PNG)
    max_len: максимальная длина текста (int)

    Returns: Image.Image (PIL) или False, если текст слишком длинный.
    """
    if isinstance(bg_image, (str, Path)):
        bg_image = Image.open(bg_image)
    tree = parse_minimessage(text)
    flat: list = []
    flatten(tree, Ctx(), flat)
    visible = sum(1 for it in flat if it is not None)
    if isinstance(max_len, int) and visible > max_len:
        return False
    bank = FontBank(Path(font_path), scale, extra_fonts or {})
    img = Renderer(bank, shadow=shadow, bg=bg, bg_image=bg_image).render(flat)
    img.save(out_path)
    return img
