import collections
import io
import json
import logging
import pathlib
from typing import Optional, List

import fpdf
import requests
import streamlit as st
from PIL import Image

logger = logging.getLogger(__name__)

CARD_HEIGHT_MM = 86
CARD_WIDTH_MM = 59

DESIRED_DPI = 300
MM_PER_INCH = 25.4
WIDTH_PX = int(CARD_WIDTH_MM * DESIRED_DPI / MM_PER_INCH)
HEIGHT_PX = int(CARD_HEIGHT_MM * DESIRED_DPI / MM_PER_INCH)

CARDS_PER_ROW = 3
CARDS_PER_COLUMN = 3
CARDS_PER_PAGE = CARDS_PER_ROW * CARDS_PER_COLUMN

# A4
PAGE_HEIGHT_MM = 297
PAGE_WIDTH_MM = 210
SPACING = 0  # between cards
TOP_MARGIN = int(
    (PAGE_HEIGHT_MM - CARD_HEIGHT_MM * CARDS_PER_COLUMN - SPACING * (CARDS_PER_COLUMN - 1)) / 2
)
LEFT_MARGIN = int(
    (PAGE_WIDTH_MM - CARD_WIDTH_MM * CARDS_PER_ROW - SPACING * (CARDS_PER_ROW - 1)) / 2
)

# approx, 怪兽 6 行, 其他 8 行
TEXTBOX_X_RATIO = 50 / 648
TEXTBOX_WIDTH_RATIO = 548 / 648
TEXTBOX_Y_RATIO = (712+2) / 948
TEXTBOX_HEIGHT_RATIO = (888 - 712) / 948
TEXTBOX_Y_RATIO_MONSTER = (738+2) / 948
TEXTBOX_HEIGHT_RATIO_MONSTER = (857 - 738) / 948

IMAGE_URL = 'https://cdn.233.momobako.com/ygopro/pics/{card_id}.jpg'


@st.cache_resource()
def read_data_tmp():
    ID2FULL_DATA = json.loads(pathlib.Path('data/cards.json').read_text(encoding='utf8'))
    ID2FULL_DATA = {x['id']: x for _, x in ID2FULL_DATA.items()}
    return ID2FULL_DATA


# ID2FULL_DATA = json.loads(pathlib.Path('data/cards.json').read_text(encoding='utf8'))
# ID2FULL_DATA = {x['id']: x for _, x in ID2FULL_DATA.items()}
ID2FULL_DATA = read_data_tmp()


@st.cache_data(max_entries=300)
def fetch_full_data(card_id: int) -> dict:
    try:
        response = requests.get(IMAGE_URL.format(card_id=card_id))
        image = Image.open(io.BytesIO(response.content))

        width, height = image.size
        rect_area = (
            int(width * TEXTBOX_X_RATIO),
            int(height * TEXTBOX_Y_RATIO),
            int(width * TEXTBOX_X_RATIO) + int(width * TEXTBOX_WIDTH_RATIO),
            int(height * TEXTBOX_Y_RATIO) + int(height * TEXTBOX_HEIGHT_RATIO),
        )
        cropped_image = image.crop(rect_area)
        pixel_colors = list(cropped_image.getdata())
        color_counter = collections.Counter(pixel_colors)
        most_common_color = color_counter.most_common(1)[0][0]

        image = image.resize((WIDTH_PX, HEIGHT_PX))
        # image.save(f'images/{card_id}.jpg')
        return {
            'image': image,
            'background_color': most_common_color,
            'data': ID2FULL_DATA.get(card_id),  # TODO
        }
    except:
        logger.exception('image for card id %s not downloadable')


def estimate_cells_needed(pdf, text, cell_width):
    segments = text.split("\n")
    total_cells_needed = 0
    for segment in segments:
        segment_width = pdf.get_string_width(segment)
        cells_needed = int(segment_width / cell_width) + 1
        total_cells_needed += cells_needed
    return total_cells_needed


# 一些修改前的效果
# ID2OLD_DESC = {
#     26202165: "【修改前效果】这张卡从场上送去墓地时，从自己的卡组把1只攻击力1500以下的怪兽加入手卡。",
#     50321796: "调整＋调整以外的怪兽1只以上\r\n【修改前效果】①：把手卡任意数量丢弃去墓地，以丢弃数量的对方场上的卡为对象才能发动。那些卡回到持有者手卡。",
#     77565204: "【修改前效果】把自己的额外卡组1只融合怪兽给双方确认，把决定的融合素材怪兽从自己卡组送去墓地。发动后第2次的自己的准备阶段时，把确认的1只融合怪兽当作融合召唤从额外卡组特殊召唤。这张卡从场上离开时，那只怪兽破坏。那只怪兽破坏时这张卡破坏。",
#     25862681: "调整＋调整以外的怪兽1只以上\r\n【修改前效果】①：1回合1次，可以从手卡把1只4星以下的怪兽特殊召唤。这个效果发动的回合，自己不能进行战斗阶段。②：1回合1次，自己的主要阶段时才能发动。场上的场地魔法卡全部破坏，自己回复1000基本分。那之后，可以从卡组把1张场地魔法卡加入手卡。",
#     21502796: "【修改前效果】反转：可以选择场上1张卡破坏。从自己卡组上面把3张卡送去墓地。",
# }


def add_cards(pdf: fpdf.FPDF, data, ID2OLD_DESC):
    x = LEFT_MARGIN
    y = TOP_MARGIN

    pdf.add_font(fname=r"simkai.ttf")
    pdf.set_text_color(0, 0, 0)  # Black

    for i, d in enumerate(data):

        if i % CARDS_PER_ROW == 0 and i != 0:
            x = LEFT_MARGIN
            y += CARD_HEIGHT_MM + SPACING

        if i % CARDS_PER_PAGE == 0 and i != 0:
            pdf.add_page()
            x = LEFT_MARGIN
            y = TOP_MARGIN

        pdf.image(d['image'], x, y, w=CARD_WIDTH_MM, h=CARD_HEIGHT_MM)

        # Place the textbox over the card image
        pdf.set_fill_color(*d['background_color'])
        is_monster = '怪兽' in d['data']['text']['types']
        text_x = x + TEXTBOX_X_RATIO * CARD_WIDTH_MM
        w = CARD_WIDTH_MM * TEXTBOX_WIDTH_RATIO
        if is_monster:
            text_y = y + CARD_HEIGHT_MM * TEXTBOX_Y_RATIO_MONSTER
            h = CARD_HEIGHT_MM * TEXTBOX_HEIGHT_RATIO_MONSTER
        else:
            text_y = y + CARD_HEIGHT_MM * TEXTBOX_Y_RATIO
            h = CARD_HEIGHT_MM * TEXTBOX_HEIGHT_RATIO
        pdf.rect(text_x, text_y, w, h, style='F')

        pdf.set_xy(text_x, text_y)
        card_text = d['data']['text']['desc']
        card_text = ID2OLD_DESC.get(d['data']['id'], card_text)

        font_size = 8
        max_height = CARD_HEIGHT_MM * TEXTBOX_HEIGHT_RATIO_MONSTER if is_monster else CARD_HEIGHT_MM * TEXTBOX_HEIGHT_RATIO
        while True:
            pdf.set_font(r"simkai", size=font_size)
            num_lines = estimate_cells_needed(pdf, card_text, w-2)
            font_size_mm = font_size * 0.352778
            if num_lines * font_size_mm < max_height:
                break
            font_size -= 0.25
        print(font_size, card_text)
        pdf.multi_cell(w, txt=card_text, border=0, align="L")
        x += CARD_WIDTH_MM + SPACING


def make_image_pdf(card_ids: List[int], ID2OLD_DESC) -> io.BytesIO:
    print(len(card_ids))
    # TODO
    data = [fetch_full_data(card_id) for card_id in card_ids]
    data = [i for i in data if i is not None]
    pdf = fpdf.FPDF(unit="mm", format="A4")
    pdf.add_page()
    add_cards(pdf, data, ID2OLD_DESC)
    return io.BytesIO(pdf.output())
