import collections
import io
import json
import logging
import pathlib
import time
from typing import List, Optional, Dict, Tuple

import pypdf
import requests
import streamlit as st

import utils
from utils import (
    ALIAS2ID_PATH, ID2DATA_PATH,
    Section, CardType, Language, CardData,
    Record, Deck,
)

logger = logging.getLogger(__name__)


@st.experimental_singleton
def read_db() -> Dict[str, CardData]:
    return json.loads(ID2DATA_PATH.read_text(encoding='utf8'))


@st.experimental_singleton
def read_alias_db() -> Dict[str, int]:
    return json.loads(ALIAS2ID_PATH.read_text(encoding='utf8'))


PDF_TEMPLATE_PATH = './KDE_DeckList.pdf'

README = pathlib.Path('README.md').read_text(encoding='utf8')
section2text = utils.sec_md(README.split('\n'))
st.markdown(section2text['foreword'])

ID2DATA = read_db()
ALIAS2ID = read_alias_db()


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


@st.cache(max_entries=500)
def fetch_new_card(card_id: int) -> Optional[CardData]:
    # it is currently single-threaded, but should be enough
    url = f'https://ygocdb.com/api/v0/?search={card_id}'
    response = requests.get(url, timeout=10)
    logger.info('Getting new card %s', card_id)
    if response.status_code != 200:
        # No retry
        logger.error('Failed getting %s: %s', url, response.text)
        return
    for d in json.loads(response.text).get('result', []):
        if d['id'] == card_id:
            return utils.adapt_dict(d)


def fetch_card_data(card_id: int) -> Optional[CardData]:
    card_id = ALIAS2ID.get(str(card_id), card_id)
    data = ID2DATA.get(str(card_id))
    if data is None:
        data = fetch_new_card(card_id)
    return data


def deck2kvs(deck: Deck, lang: Language) -> Tuple[Dict, Dict[str, List[Record]]]:
    final_dict = {}

    main_type_idx = {t: 0 for t in CardType}
    main_type_count = {t: 0 for t in CardType}
    main_type_overflow: Dict[str, List[Record]] = {t: [] for t in CardType}
    main_type_overflow.update({'Unknown': []})
    for record in deck.main:
        card_type = record.type
        if card_type is None:
            main_type_overflow['Unknown'].append(record)
            continue
        main_type_idx[card_type] += 1
        idx = main_type_idx[card_type]
        main_type_count[card_type] += record.count
        if idx > 18:
            main_type_overflow[card_type].append(record)
        final_dict.update(
            {
                f'{card_type} {idx}': getattr(record, lang),
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
                f'Extra Deck {idx}': getattr(record, lang),
                f'Extra Deck {idx} Count': record.count,
            }
        )
        count += record.count
    final_dict['Total Extra Deck'] = count

    count = 0
    for idx, record in enumerate(deck.side, start=1):
        final_dict.update(
            {
                f'Side Deck {idx}': getattr(record, lang),
                f'Side Deck {idx} Count': record.count,
            }
        )
        count += record.count
    final_dict['Total Side Deck'] = count

    return final_dict, main_type_overflow


def make_pdf(kvs: Dict) -> io.BytesIO:
    reader = pypdf.PdfReader(PDF_TEMPLATE_PATH)
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[0])
    writer.update_page_form_field_values(writer.pages[0], kvs)

    content = io.BytesIO()
    writer.write(content)
    return content


uploaded_file = st.file_uploader('**拖拽上传 ydk 文件**', type='ydk')
if uploaded_file is not None:
    start_time = time.perf_counter()

    text = io.StringIO(uploaded_file.getvalue().decode("utf-8")).read(1000)
    logger.info(
        '[filename]: %s | [content]: %s',
        uploaded_file.name, json.dumps(text),
    )

    deck = ydk2deck(text.split('\n'))

    for section in Section:
        for record in getattr(deck, section):
            card_data = fetch_card_data(record.card_id)
            if card_data is None:
                record.name_cn = '未找到该卡'
                continue
            record.type = card_data['type']
            if name_cn := card_data.get('sc_name'):
                record.name_cn = name_cn  # 简中
            else:
                if name_cn := card_data.get('cn_name'):
                    record.name_cn = '(旧译) ' + name_cn
                else:
                    record.name_cn = '(没找到中文译名)'
            record.name_jp = card_data.get('jp_name', '(没找到日文译名)')
            record.name_en = card_data.get('en_name', '(没找到英文译名)')

    pdf_name = uploaded_file.name
    if pdf_name.endswith('.ydk'):
        pdf_name = pdf_name[:-len('.ydk')]
    pdf_name = pdf_name + '.pdf'

    final_dict, _ = deck2kvs(deck, lang=Language.JAPANESE)
    with make_pdf(final_dict) as content:
        st.download_button('下载日文卡表 JP', content, file_name='日文@' + pdf_name)

    final_dict, _ = deck2kvs(deck, lang=Language.CHINESE)
    with make_pdf(final_dict) as content:
        st.download_button('下载简中卡表 CN', content, file_name='简中@' + pdf_name)

    final_dict, main_type_overflow = deck2kvs(deck, lang=Language.ENGLISH)
    with make_pdf(final_dict) as content:
        st.download_button('下载英文卡表 EN', content, file_name='英文@' + pdf_name)

    elapsed = time.perf_counter() - start_time
    if elapsed < 1:
        elapsed = f'{elapsed * 100:.1f} ms'
    else:
        elapsed = f'{elapsed:.3f} s'
    st.write(f'Elapsed {elapsed}')

    if any(records for t, records in main_type_overflow.items()):
        st.markdown('**写不下或无法识别的卡片**')
        for t in main_type_overflow:
            main_type_overflow[t] = [record.__dict__ for record in main_type_overflow[t]]
        st.write(main_type_overflow)

st.markdown(section2text['说明'])
