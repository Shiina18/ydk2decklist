import io
import json
import pathlib
import sqlite3
import zipfile

import pandas as pd
import requests

import utils

RAW_DB_DIR = pathlib.Path('.db')

# download automatically; should update regularly
# https://ygocdb.com/about
CARDS_JSON_PATH = RAW_DB_DIR / 'cards.json'
SOURCE_CARDS_JSON_URL = 'https://ygocdb.com/api/v0/cards.zip'
VERSION_PATH = RAW_DB_DIR / 'cards.json.version'
VERSION_URL = 'https://ygocdb.com/api/v0/cards.zip.md5?callback=gu'

version = None
should_update = False
response = requests.get(VERSION_URL)
if response.status_code == 200:
    if VERSION_PATH.exists():
        version = VERSION_PATH.read_text()
    should_update = response.text != version
    version = response.text
else:
    raise Exception(response.text)

if should_update:
    response = requests.get(SOURCE_CARDS_JSON_URL)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(RAW_DB_DIR)
        VERSION_PATH.write_text(version)
    else:
        raise Exception(response.text)

dict_raw = json.loads(CARDS_JSON_PATH.read_text(encoding='utf8'))
dict_small = {}
for cid, d in dict_raw.items():
    if 'data' not in d:
        continue
    dict_small[d['id']] = utils.adapt_dict(d)
utils.ID2DATA_PATH.write_text(
    json.dumps(dict_small, ensure_ascii=False, indent=2),
    encoding='utf8',
)

# download manually; no need to update regularly
# https://github.com/mycard/ygopro-database/raw/master/locales/zh-CN/cards.cdb
CARDS_CDB_PATH = RAW_DB_DIR / 'cards.cdb'

# normalize card id for cards with alternate artworks
with sqlite3.connect(CARDS_CDB_PATH) as connection:
    df_data = pd.read_sql(
        'SELECT texts.name, datas.id, datas.alias '
        'FROM datas JOIN texts ON datas.id = texts.id '
        'WHERE datas.alias != 0',
        connection,
    )

alias2id = dict(zip(df_data['alias'], df_data['id']))
alias2id_small = {}
for alias, id_ in alias2id.items():
    if id_ in dict_small:
        alias2id_small[alias] = id_
    if alias in dict_small:
        alias2id_small[id_] = alias
utils.ALIAS2ID_PATH.write_text(json.dumps(alias2id_small, indent=2))
