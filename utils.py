import dataclasses
import enum
import pathlib
from typing import List, Optional, Dict, Union

ALIAS2ID_PATH = pathlib.Path('alias2id.json')
ID2DATA_PATH = pathlib.Path('id2data.json')

CardData = Dict[str, Union[Optional[str]]]


class StrEnum(str, enum.Enum):
    pass


class Section(StrEnum):
    MAIN = 'main'
    EXTRA = 'extra'
    SIDE = 'side'


class CardType(StrEnum):
    MONSTER = 'Monster'
    SPELL = 'Spell'
    TRAP = 'Trap'


class Language(StrEnum):
    CHINESE = 'name_cn'
    JAPANESE = 'name_jp'
    ENGLISH = 'name_en'


@dataclasses.dataclass
class Record:
    card_id: int
    name_cn: Optional[str] = None
    name_jp: Optional[str] = None
    name_en: Optional[str] = None
    count: int = 0
    type: Optional[CardType] = None


@dataclasses.dataclass
class Deck:
    main: List[Record] = dataclasses.field(default_factory=list)
    extra: List[Record] = dataclasses.field(default_factory=list)
    side: List[Record] = dataclasses.field(default_factory=list)


def parse_type(num: int) -> CardType:
    """https://github.com/KittyTrouble/Ygopro-Card-Creation#step-4b-choosing-a-cards-type"""
    binary = bin(num)
    if binary[-1] == '1':
        return CardType.MONSTER
    if binary[-2] == '1':
        return CardType.SPELL
    if binary[-3] == '1':
        return CardType.TRAP


def adapt_dict(d: dict) -> dict:
    tmp = {'type': parse_type(d['data']['type'])}
    for field in ['cn_name', 'sc_name', 'jp_name', 'en_name']:
        if field in d:
            tmp.update({field: d[field]})
    return tmp


def sec_md(lines: List[str]) -> Dict[str, str]:
    section2text = {}
    section = 'foreword'
    buffer = []
    for line in lines:
        if line.startswith('##') and not line.startswith('###'):
            section2text[section] = '\n'.join(buffer)
            buffer = []
            section = line[len('## '):]
        buffer.append(line)
    if buffer:
        section2text[section] = '\n'.join(buffer)
    return section2text


README = pathlib.Path('README.md').read_text(encoding='utf8')
section2text = sec_md(README.split('\n'))
