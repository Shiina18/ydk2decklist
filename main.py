import collections
import dataclasses
import datetime
import io
import json
import pathlib
import sqlite3
from typing import List, Optional, Dict, Set, Tuple

import pandas as pd
import pypdf
import streamlit as st
from strenum import StrEnum

PDF_TEMPLATE_PATH = './KDE_DeckList.pdf'
LUA_SCRIPT_DIR = './script'
CARD_DATABASE_PATH = './cards.cdb'
# source: https://ygocdb.com/about
DOVE_DATABASE_PATH = './cards.json'
_DICT_DATA_RAW = json.loads(pathlib.Path(DOVE_DATABASE_PATH).read_text(encoding='utf8'))
DICT_DATA = {}
for cid, d in _DICT_DATA_RAW.items():
    DICT_DATA[d['id']] = d


class Section(StrEnum):
    MAIN = 'main'
    EXTRA = 'extra'
    SIDE = 'side'


class CardType(StrEnum):
    MONSTER = 'Monster'
    SPELL = 'Spell'
    TRAP = 'Trap'


@dataclasses.dataclass
class Record:
    card_id: int
    name_jp: Optional[str] = None
    name_cn: Optional[str] = None
    count: int = 0
    type: Optional[CardType] = None


@dataclasses.dataclass
class Deck:
    main: List[Record] = dataclasses.field(default_factory=list)
    extra: List[Record] = dataclasses.field(default_factory=list)
    side: List[Record] = dataclasses.field(default_factory=list)


def ydk2deck(lines: List[str]) -> Deck:
    section2ids: Dict[str, List[int]] = {s: [] for s in Section}
    current_section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == '#main':
            current_section = Section.MAIN
        elif line == '#extra':
            current_section = Section.EXTRA
        elif line == '!side':
            current_section = Section.SIDE
        elif current_section is not None:
            # ensure the content is a number
            section2ids[current_section].append(int(line))

    deck = Deck()
    for section, ids in section2ids.items():
        for card_id, count in collections.Counter(ids).items():
            getattr(deck, section).append(Record(card_id=card_id, count=count))

    return deck


def get_unique_ids(deck: Deck) -> Set[int]:
    unique_ids = set()
    for section in Section:
        unique_ids = unique_ids | set(record.card_id for record in getattr(deck, section))
    return unique_ids


def parse_type(num: int) -> CardType:
    """https://github.com/KittyTrouble/Ygopro-Card-Creation#step-4b-choosing-a-cards-type"""
    binary = bin(num)
    if binary[-1] == '1':
        return CardType.MONSTER
    if binary[-2] == '1':
        return CardType.SPELL
    if binary[-3] == '1':
        return CardType.TRAP


def deck2kvs(deck: Deck, lang='jp') -> Tuple[Dict, Dict[CardType, List[Record]]]:
    name = f'name_{lang}'
    final_dict = {}

    main_type_idx = {t: 0 for t in CardType}
    main_type_count = {t: 0 for t in CardType}
    main_type_overflow: Dict[CardType, List[Record]] = {t: [] for t in CardType}
    for record in deck.main:
        card_type = record.type
        main_type_idx[card_type] += 1
        idx = main_type_idx[card_type]
        main_type_count[card_type] += record.count
        if idx > 18:
            main_type_overflow[card_type].append(record)
        final_dict.update(
            {
                f'{card_type} {idx}': getattr(record, name),
                f'{card_type} Card {idx} Count': record.count,
            }
        )
    for t in CardType:
        final_dict[f'Total {t} Cards'] = main_type_count[t]
    final_dict['Main Deck Total'] = sum(main_type_count[t] for t in CardType)

    count = 0
    for idx, record in enumerate(deck.extra, start=1):
        final_dict.update(
            {
                f'Extra Deck {idx}': getattr(record, name),
                f'Extra Deck {idx} Count': record.count,
            }
        )
        count += record.count
    final_dict['Total Extra Deck'] = count

    count = 0
    for idx, record in enumerate(deck.side, start=1):
        final_dict.update(
            {
                f'Side Deck {idx}': getattr(record, name),
                f'Side Deck {idx} Count': record.count,
            }
        )
        count += record.count
    final_dict['Total Side Deck'] = count

    return final_dict, main_type_overflow


def make_pdf(kvs: Dict):
    now = datetime.datetime.now()
    kvs.update(
        {
            'Event Date - Year': now.year,
            'Event Date - Month': f'{now.month:0>2}',
            'Event Date - Day': f'{now.day:0>2}',
        }
    )

    reader = pypdf.PdfReader(PDF_TEMPLATE_PATH)
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[0])
    writer.update_page_form_field_values(writer.pages[0], kvs)

    content = io.BytesIO()
    writer.write(content)
    return content


def fetch_name_jp(row) -> str:
    card_id = row.id if row.alias == 0 else row.alias
    path = pathlib.Path(LUA_SCRIPT_DIR) / f'c{card_id}.lua'
    if not path.exists():
        return f'card_id {row.id} not found'
    with open(path, encoding='utf8') as f:
        line = f.readline().strip()
    assert line.startswith('--')
    return line[len('--'):]


def fetch_name_cn(row) -> str:
    card_id = row.id if row.alias == 0 else row.alias
    d = DICT_DATA.get(card_id)
    if d is None:
        return f'card_id {row.id} not found'
    name_cn = d.get('sc_name')
    if name_cn is not None:
        return name_cn
    return '(旧译) ' + d.get('cn_name')


INTRODUCTION = pathlib.Path('README.md').read_text(encoding='utf8')
st.markdown(INTRODUCTION)

connection = sqlite3.connect(CARD_DATABASE_PATH)

uploaded_file = st.file_uploader("上传 ydk 文件")
if uploaded_file is not None:
    bytes_data = uploaded_file.getvalue()
    lines = io.StringIO(uploaded_file.getvalue().decode("utf-8")).readlines()
    assert len(lines) < 100

    deck = ydk2deck(lines)
    unique_ids = get_unique_ids(deck)

    df_data = pd.read_sql(
        f'SELECT datas.id, datas.alias, datas.type, texts.name AS name_cn '
        f'FROM datas JOIN texts ON datas.id = texts.id '
        f'WHERE datas.id IN {tuple(unique_ids)} '
        f'OR datas.alias IN {tuple(unique_ids)}',
        connection,
    )

    df_data['type'] = df_data['type'].apply(parse_type)
    df_data['name_jp'] = df_data.apply(fetch_name_jp, axis=1)
    df_data['name_cn'] = df_data.apply(fetch_name_cn, axis=1)
    for section in Section:
        for record in getattr(deck, section):
            row = df_data[df_data['id'] == record.card_id].iloc[0]
            record.type = row.type
            record.name_cn = row.name_cn
            record.name_jp = row.name_jp

    pdf_name = uploaded_file.name
    if pdf_name.endswith('.ydk'):
        pdf_name = pdf_name[:-len('.ydk')]
    pdf_name = pdf_name + '.pdf'

    final_dict, _ = deck2kvs(deck, lang='jp')
    content = make_pdf(final_dict)
    st.download_button('下载日文卡表', content, file_name='日文_' + pdf_name)

    final_dict, main_type_overflow = deck2kvs(deck, lang='cn')
    content = make_pdf(final_dict)
    st.download_button('下载简中卡表', content, file_name='简中_' + pdf_name)

    if any(records for t, records in main_type_overflow.items()):
        st.markdown('**写不下的卡片**')
        for t in main_type_overflow:
            main_type_overflow[t] = [record.__dict__ for record in main_type_overflow[t]]
        st.write(main_type_overflow)
