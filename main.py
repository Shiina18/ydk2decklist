import collections
import hashlib
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
    ALIAS2ID_PATH, ID2DATA_PATH, OLD2ID_PATH,
    Section, CardType, Language, CardData,
    Record, Deck,
)
import printing_utils

logger = logging.getLogger(__name__)

TTL = 60 * 60 * 12

hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)


@st.cache_resource(ttl=TTL)
def read_db() -> Dict[str, CardData]:
    return json.loads(ID2DATA_PATH.read_text(encoding='utf8'))


@st.cache_resource(ttl=TTL)
def read_alias_db() -> Dict[str, int]:
    return json.loads(ALIAS2ID_PATH.read_text(encoding='utf8'))


@st.cache_resource(ttl=TTL)
def read_old_db() -> Dict[str, int]:
    return json.loads(OLD2ID_PATH.read_text(encoding='utf8'))


@st.cache_resource
def read_adapter() -> Dict[str, int]:
    return json.loads(pathlib.Path('adapter.json').read_text(encoding='utf8'))


@st.cache_resource
def read_adapter_en() -> Dict[str, int]:
    return json.loads(pathlib.Path('adapter_en.json').read_text(encoding='utf8'))


@st.cache_resource(ttl=TTL)
def read_readme():
    README = pathlib.Path('README.md').read_text(encoding='utf8')
    return utils.sec_md(README.split('\n'))


section2text = read_readme()
st.markdown(section2text['foreword'])

FILL_MONSTER_IN_SPELL = st.checkbox(
    '写不下的怪兽自动填到魔法栏底部',
    value=True,
    help='不勾选则输出到页面; 勾选了但魔法栏也写不下亦输出到页面',
)
USE_CHINESE = st.checkbox('使用中文 PDF 模板')
NOTE = '**中文模板常常显示不全卡名, 英文模板几乎没有这个问题**'

PRINT_IMAGE = st.checkbox('打印卡图')
if PRINT_IMAGE:
    st.text('生成卡图打印文件需要一些时间 (可能十几秒). 其余注意事项见页面底部.')
    ID2OLD_DESC = {}
    st.markdown(
        """如果你需要打印修改前的效果, 可以自己提供配置. 样例

```json
{
    "26202165": "【修改前效果】这张卡从场上送去墓地时，从自己的卡组把1只攻击力1500以下的怪兽加入手卡。",
    "50321796": "调整＋调整以外的怪兽1只以上\\r\\n【修改前效果】①：把手卡任意数量丢弃去墓地，以丢弃数量的对方场上的卡为对象才能发动。那些卡回到持有者手卡。",
    "77565204": "【修改前效果】把自己的额外卡组1只融合怪兽给双方确认，把决定的融合素材怪兽从自己卡组送去墓地。发动后第2次的自己的准备阶段时，把确认的1只融合怪兽当作融合召唤从额外卡组特殊召唤。这张卡从场上离开时，那只怪兽破坏。那只怪兽破坏时这张卡破坏。",
    "25862681": "调整＋调整以外的怪兽1只以上\\r\\n【修改前效果】①：1回合1次，可以从手卡把1只4星以下的怪兽特殊召唤。这个效果发动的回合，自己不能进行战斗阶段。②：1回合1次，自己的主要阶段时才能发动。场上的场地魔法卡全部破坏，自己回复1000基本分。那之后，可以从卡组把1张场地魔法卡加入手卡。",
    "21502796": "【修改前效果】反转：可以选择场上1张卡破坏。从自己卡组上面把3张卡送去墓地。"
}
```"""
    )
    json_input = st.text_area("高级配置, 输入完成后按 ctrl+enter, 下面显示 ok 表示配置成功", height=200)
    try:
        ID2OLD_DESC = json.loads(json_input)
        ID2OLD_DESC = {int(k): v for k, v in ID2OLD_DESC.items()}
        st.text("ok")
    except json.JSONDecodeError:
        st.text("Invalid JSON format")


TEMPLATE = Language.CHINESE if USE_CHINESE else Language.ENGLISH
EN_PDF_TEMPLATE_PATH = './KDE_DeckList.pdf'  # 上限 18 条, 自动放缩文字
CN_PDF_TEMPLATE_PATH = './中文卡表模板.pdf'  # 上限 20 条, 不放缩文字, 经常显示不全
if TEMPLATE == Language.ENGLISH:
    ADAPTER = read_adapter_en()
else:
    ADAPTER = read_adapter()

ID2DATA = read_db()
ALIAS2ID = read_alias_db()
OLD2ID = read_old_db()


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


@st.cache_data(ttl=TTL)
def fetch_new_card(card_id: int) -> Optional[CardData]:
    # it is currently single-threaded, but should be enough
    url = f'https://ygocdb.com/api/v0/?search={card_id}'
    try:
        # TODO: No retry now
        response = requests.get(url, timeout=10)
    except:
        logger.exception('')
        return
    logger.info('Getting new card %s', card_id)
    if response.status_code != 200:
        logger.error('Failed getting %s: %s', card_id, response.text)
        return

    results = response.json().get('result', [])
    if len(results) == 1:
        d = results[0]
        if d['id'] != card_id:
            # TODO: 不清楚这些卡 id 怎么关联上的
            logger.warning('Different id for %s: %s', card_id, utils.adapt_dict(d))
        return utils.adapt_dict(d)

    logger.info('Fetched %s: %s', card_id, results)
    for d in results:
        if d['id'] == card_id:
            return utils.adapt_dict(d)

    logger.error('%s not found', card_id)


def fetch_card_data(card_id: int) -> Optional[CardData]:
    data = ID2DATA.get(str(card_id))

    if data is None:
        # 老 id 转换
        card_id = OLD2ID.get(str(card_id), card_id)
        data = ID2DATA.get(str(card_id))

    if data is None:
        # 关联异画卡
        norm_card_id = ALIAS2ID.get(str(card_id), card_id)
        data = ID2DATA.get(str(norm_card_id))

    if data is not None:
        return data

    data = fetch_new_card(card_id)
    return data


def get_standard_card_id(card_id: int) -> Optional[int]:
    """TODO: quite duplicate with `fetch_card_data`"""
    data = ID2DATA.get(str(card_id))
    if data is not None:
        return card_id

    # 老 id 转换
    card_id = OLD2ID.get(str(card_id), card_id)
    data = ID2DATA.get(str(card_id))
    if data is not None:
        return card_id

    # 关联异画卡
    norm_card_id = ALIAS2ID.get(str(card_id), card_id)
    data = ID2DATA.get(str(norm_card_id))
    if data is not None:
        return norm_card_id

    data = fetch_new_card(card_id)
    if data is not None:
        return card_id

    logger.error('card id %s not found', card_id)


def deck2kvs(
    deck: Deck, lang: Language, fill_monster_in_spell: bool = False,
) -> Tuple[Dict, Dict[str, List[Record]]]:
    final_dict = {}

    main_type_idx = {t: 0 for t in CardType}
    main_type_count = {t: 0 for t in CardType}
    main_type_overflow: Dict[str, List[Record]] = {t: [] for t in CardType}
    main_type_overflow.update({'Unknown': []})
    max_rows = 18 if TEMPLATE == lang.ENGLISH else 20
    for record in deck.main:
        card_type = record.type
        if card_type is None:
            main_type_overflow['Unknown'].append(record)
            continue
        main_type_idx[card_type] += 1
        idx = main_type_idx[card_type]
        main_type_count[card_type] += record.count
        if idx > max_rows:
            main_type_overflow[card_type].append(record)
        final_dict.update(
            {
                ADAPTER.get(f'{card_type} {idx}', 'null'): getattr(record, lang),
                ADAPTER.get(f'{card_type} Card {idx} Count', 'null'): record.count,
            }
        )
    for t in CardType:
        final_dict[ADAPTER[f'Total {t} Cards']] = main_type_count[t]
    final_dict[ADAPTER['Main Deck Total']] = sum(main_type_count[t] for t in CardType)

    # 怪兽太多时填到魔法栏, 从底部往上填, 和最后一张魔法卡至少空两行, 还有多余的怪兽输出到页面
    if fill_monster_in_spell and main_type_overflow[CardType.MONSTER]:
        num_filled_monsters = 0
        num_unique_spells = main_type_idx[CardType.SPELL]

        for minus_idx in range(len(main_type_overflow[CardType.MONSTER])):
            # 魔法栏也填满了
            if minus_idx + num_unique_spells + 2 >= max_rows:
                continue

            num_filled_monsters += 1
            record = main_type_overflow[CardType.MONSTER].pop()
            final_dict.update(
                {
                    ADAPTER.get(f'{CardType.SPELL} {max_rows - minus_idx}', 'null'):
                        getattr(record, lang),
                    ADAPTER.get(f'{CardType.SPELL} Card {max_rows - minus_idx} Count', 'null'):
                        record.count,
                }
            )

        if num_filled_monsters > 0:
            final_dict.update(
                {
                    ADAPTER.get(
                        f'{CardType.SPELL} {max_rows - num_filled_monsters}', 'null'
                    ): '===以下怪兽===以上魔法===',
                }
            )

    count = 0
    for idx, record in enumerate(deck.extra, start=1):
        final_dict.update(
            {
                ADAPTER.get(f'Extra Deck {idx}', 'null'): getattr(record, lang),
                ADAPTER.get(f'Extra Deck {idx} Count', 'null'): record.count,
            }
        )
        count += record.count
    final_dict[ADAPTER['Total Extra Deck']] = count
    final_dict[ADAPTER['Extra Deck Total']] = count

    count = 0
    for idx, record in enumerate(deck.side, start=1):
        final_dict.update(
            {
                ADAPTER.get(f'Side Deck {idx}', 'null'): getattr(record, lang),
                ADAPTER.get(f'Side Deck {idx} Count', 'null'): record.count,
            }
        )
        count += record.count
    final_dict[ADAPTER['Total Side Deck']] = count
    final_dict[ADAPTER['Side Deck Total']] = count

    return final_dict, main_type_overflow


@st.cache_resource
def read_template_pdf():
    reader = pypdf.PdfReader(CN_PDF_TEMPLATE_PATH)
    return reader.pages[0]


@st.cache_resource
def read_template_pdf_en():
    reader = pypdf.PdfReader(EN_PDF_TEMPLATE_PATH)
    return reader.pages[0]


def make_pdf(kvs: Dict, lang: Language) -> io.BytesIO:
    writer = pypdf.PdfWriter()
    if lang == Language.ENGLISH:
        writer.add_page(read_template_pdf_en())
    elif lang == Language.CHINESE:
        writer.add_page(read_template_pdf())
    writer.update_page_form_field_values(writer.pages[0], kvs)

    content = io.BytesIO()
    writer.write(content)
    return content


# note that streamlit will rerun the script when the user clicks the download button
uploaded_file = st.file_uploader(NOTE, type='ydk')
if uploaded_file is not None:
    start_time = time.perf_counter()

    text = io.StringIO(uploaded_file.getvalue().decode("utf-8")).read(2000)
    md5 = hashlib.md5(text.encode()).hexdigest()
    logger.info(
        '[filename] %s [md5] %s [content] %s',
        uploaded_file.name, md5, json.dumps(text),
    )

    deck = ydk2deck(text.split('\n'))
    card_ids = []

    for section in Section:
        for record in getattr(deck, section):
            card_data = fetch_card_data(record.card_id)
            card_ids += [get_standard_card_id(record.card_id)] * record.count
            if card_data is None:
                record.name_cn = f'{record.card_id} 未找到该卡'
                continue
            record.type = card_data['type']
            if name_cn := card_data.get('sc_name'):
                record.name_cn = name_cn  # 简中
            else:
                if name_cn := card_data.get('cn_name'):
                    record.name_cn = '(旧译) ' + name_cn
                else:
                    record.name_cn = f'({record.card_id} 没找到中文译名)'
            record.name_jp = card_data.get('jp_name', f'({record.card_id} 没找到日文译名)')
            record.name_en = card_data.get('en_name', f'({record.card_id} 没找到英文译名)')

    pdf_name = uploaded_file.name
    if pdf_name.endswith('.ydk'):
        pdf_name = pdf_name[:-len('.ydk')]
    pdf_name = pdf_name + '.pdf'

    final_dict, _ = deck2kvs(deck, lang=Language.JAPANESE, fill_monster_in_spell=FILL_MONSTER_IN_SPELL)
    with make_pdf(final_dict, TEMPLATE) as content:
        st.download_button('下载日文卡表 JP', content, file_name='日文@' + pdf_name)

    final_dict, _ = deck2kvs(deck, lang=Language.CHINESE, fill_monster_in_spell=FILL_MONSTER_IN_SPELL)
    with make_pdf(final_dict, TEMPLATE) as content:
        st.download_button('下载简中卡表 CN', content, file_name='简中@' + pdf_name)

    final_dict, main_type_overflow = deck2kvs(deck, lang=Language.ENGLISH, fill_monster_in_spell=FILL_MONSTER_IN_SPELL)
    with make_pdf(final_dict, TEMPLATE) as content:
        st.download_button('下载英文卡表 EN', content, file_name='英文@' + pdf_name)

    if PRINT_IMAGE:
        with printing_utils.make_image_pdf(card_ids, ID2OLD_DESC) as content:
            st.download_button('下载可打印中文卡图', content, file_name='中文卡图打印@' + pdf_name)


    elapsed = time.perf_counter() - start_time
    if elapsed < 1:
        elapsed = f'{elapsed * 1000:.1f} ms'
    else:
        elapsed = f'{elapsed:.3f} s'
    logger.info('[md5] %s [elapsed] %s', md5, elapsed)

    if any(records for t, records in main_type_overflow.items()):
        st.markdown('**写不下或无法识别的卡片**')
        for t in main_type_overflow:
            main_type_overflow[t] = [record.__dict__ for record in main_type_overflow[t]]
        st.write(main_type_overflow)

st.warning('打印卡表后建议自己卡检一遍——只有你能为自己负责')
st.markdown(section2text['说明'])

with st.expander('Changelog'):
    st.markdown(utils.remove_title(section2text['Changelog']))


FOOTER = 'Made with dove by <a href="https://mp.weixin.qq.com/s/VCS4aBVqPKbDwCcGf9RpXQ">C7</a>'
st.markdown(
    f"<div style='text-align: center;'><font color='lightgrey'>{FOOTER}</font></div>",
    unsafe_allow_html=True,
)
