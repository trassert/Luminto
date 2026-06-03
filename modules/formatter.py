import re

from loguru import logger
from pymorphy3 import MorphAnalyzer
from telethon.extensions import markdown
from telethon import types

logger.info(f"Загружен модуль {__name__}!")


morph = MorphAnalyzer()
zalgo_pattern = re.compile(
    r"[\u0300-\u036F\u0483-\u0489\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06ED\u0901-\u0903\u093C\u093E-\u094F\u0951-\u0957\u0962\u0963\u0981\u09BC\u09BE-\u09C4\u09C7\u09C8\u09CB-\u09CD\u09D7\u09E2\u09E3\u0A01\u0A02\u0A3C\u0A40-\u0A42\u0A47\u0A48\u0A4B-\u0A4D\u0A51\u0A70\u0A71\u0A75\u0A81\u0A82\u0ABC\u0AC1-\u0AC5\u0AC7\u0AC8\u0ACD\u0AE2\u0AE3\u0B01\u0B3C\u0B3E-\u0B44\u0B47\u0B48\u0B4B-\u0B4D\u0B56\u0B57\u0B62\u0B63\u0B82\u0BBE\u0BC0\u0BC2\u0BC6-\u0BC8\u0BCA-\u0BCC\u0BD7\u0C00\u0C04\u0C3E-\u0C44\u0C46-\u0C48\u0C4A-\u0C4D\u0C55\u0C56\u0C62\u0C63\u0C82\u0C83\u0CBC\u0CBF\u0CC6\u0CCC\u0CCD\u0CE2\u0CE3\u0D02\u0D03\u0D3E-\u0D44\u0D46-\u0D48\u0D4A-\u0D4D\u0D57\u0D62\u0D63\u0D82\u0D83\u0DCF-\u0DD4\u0DD6\u0DD8-\u0DDF\u0DF2\u0DF3\u0E31\u0E34-\u0E3A\u0E47-\u0E4E\u0EB1\u0EB4-\u0EB9\u0EBB\u0EBC\u0EC8-\u0ECD\u0F18\u0F19\u0F35\u0F37\u0F39\u0F3E\u0F3F\u0F71-\u0F84\u0F86\u0F87\u0F8D-\u0F97\u0F99-\u0FBC\u0FC6\u102D-\u1030\u1032\u1036\u1037\u1039\u1058\u1059\u109D\u135D-\u135F\u1712-\u1714\u1732-\u1734\u1752\u1753\u1772\u1773\u17B4-\u17D3\u17DD\u180B-\u180D\u18A9\u1920-\u192B\u1930-\u193B\u1A17\u1A18\u1A55\u1A57\u1A60-\u1A7C\u1A7F\u1AB0-\u1AC0\u1B00-\u1B04\u1B34\u1B36-\u1B44\u1B6B-\u1B73\u1B80-\u1B82\u1BA1-\u1BAD\u1BE6-\u1BF3\u1C24-\u1C37\u1CD0-\u1CED\u1D00-\u1DBF\u1E00-\u1EFF\u200B-\u200F\u202A-\u202E\u2060-\u206F\u20D0-\u20EF\u302A-\u302F\u3099\u309A\uA806\uA80B\uA825\uA826\uFB1E\uFE00-\uFE0F\uFE20-\uFE2F\uFEFF\uFFF9-\uFFFB]",
)


def value_to_str(number, noun) -> str:
    """Склоняет существительное в соответствии с числом.

    Аргументы:
        number: Число.
        noun: Существительное в именительном падеже единственного числа.

    Возвращает:
        Строка с числом и склоненным существительным.
    """
    p = morph.parse(noun)[0]

    if str(number)[0] == "1" and len(str(number)) == 2:
        word = p.inflect({"gent", "plur"}).word
    else:
        match abs(number) % 10:
            case 1:
                word = p.inflect({"nomn", "sing"}).word
            case 2 | 3 | 4:
                word = p.inflect({"gent", "sing"}).word
            case _:
                word = p.inflect({"gent", "plur"}).word
    return f"{number} {word}"


def rm_badtext(text):
    text = re.sub(r"\\boxed\{.*?\}", "", text)
    return text.replace("$", "**").replace(
        "\\cdot",
        "×",
    )  # ! Экранизация необходима


def rm_colors(text):
    """Удаляет из текста все вхождения "§n", где n - цифра или буква."""
    pattern = r"§[a-zA-Z0-9]"
    return re.sub(pattern, "", text)


def splitter(text, chunk_size=4096):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def check_zalgo(text):
    return (len(zalgo_pattern.findall(text)) / len(text)) * 100


def city_last_letter(city: str) -> str:
    city = city.strip().lower()
    excluded_letters = {"ь", "ъ", "ы"}
    for i in range(len(city) - 1, -1, -1):
        if city[i] not in excluded_letters:
            return city[i]
    return city[-1]  # fallback


def fmtime(s: float) -> str:
    s = int(s)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    units = [(h, "ч."), (m, "мин."), (s, "сек.")]
    parts = [f"{v} {u}" for v, u in units if v > 0]
    return ", ".join(parts) if parts else "0 сек."


def is_valid_mc_nick(nick: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_]{3,16}", nick))


def parse_pings_strict(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"- (\d+)ms", text)]


class CustomMarkdown:
    """
    Костыль для работы с маркдауном.
    Не работает нормально жирность с цитатами, keep in mind!
    Поддерживает:
    - Цитата >
    - Сокр. цитата >>
    - Спойлер [text] (spoiler)
    - Прем. эмодзи [text] (emoji/123456789)
    """

    @staticmethod
    def parse(text):
        if ("> " not in text) or (
            not any(line.startswith(("> ", ">> ")) for line in text.split("\n"))
        ):
            text, entities = markdown.parse(text)
        else:
            lines = text.split("\n")
            new_lines = []
            blockquotes = []
            offset = 0

            for line in lines:
                if line.startswith(">> "):
                    clean = line[3:]
                    collapsed = True
                elif line.startswith("> "):
                    clean = line[2:]
                    collapsed = False
                else:
                    new_lines.append(line)
                    offset += len(line) + 1
                    continue

                ln = len(clean)
                if ln > 0:
                    blockquotes.append((offset, ln, collapsed))
                new_lines.append(clean)
                offset += ln + 1

            text = "\n".join(new_lines)
            text, entities = markdown.parse(text)

            for off, length, collapsed in reversed(blockquotes):
                entities.append(
                    types.MessageEntityBlockquote(
                        offset=off,
                        length=length,
                        collapsed=collapsed or None,
                    ),
                )

        for i, e in enumerate(entities):
            if isinstance(e, types.MessageEntityTextUrl):
                if e.url == "spoiler":
                    entities[i] = types.MessageEntitySpoiler(e.offset, e.length)
                elif e.url.startswith("emoji/"):
                    entities[i] = types.MessageEntityCustomEmoji(
                        e.offset,
                        e.length,
                        int(e.url.split("/", 1)[1]),
                    )
        return text, entities

    @staticmethod
    def unparse(text, entities):
        filtered = [
            e
            for e in (entities or [])
            if not isinstance(e, types.MessageEntityBlockquote)
        ]
        for i, e in enumerate(filtered):
            if isinstance(e, types.MessageEntityCustomEmoji):
                filtered[i] = types.MessageEntityTextUrl(
                    e.offset,
                    e.length,
                    f"emoji/{e.document_id}",
                )
            elif isinstance(e, types.MessageEntitySpoiler):
                filtered[i] = types.MessageEntityTextUrl(e.offset, e.length, "spoiler")
        return markdown.unparse(text, filtered)
