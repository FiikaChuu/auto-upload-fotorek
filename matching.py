import re

def number(value):
    match = re.match(r'^(\d+)(?=$|[\s._-])', str(value).strip())
    return int(match[1]) if match else None


def detect(rows):
    aliases = {'no': {'no', 'nomor', 'number'}, 'pic': {'pic', 'penanggungjawab'},
               'link': {'linkdrive', 'linkgoogledrive', 'tautandrive'}}
    for index, row in enumerate(rows):
        found = {}
        for col, value in enumerate(row):
            normalized = re.sub(r'[^a-z0-9]', '', str(value).lower())
            for name, options in aliases.items():
                if normalized in options:
                    if name in found:
                        raise ValueError('Header kolom ganda; rapikan header terlebih dahulu.')
                    found[name] = col
        if len(found) == 3:
            return index, found
    raise ValueError('Header No., PIC, dan Link Drive tidak ditemukan dalam 50 baris pertama.')


def column(index):
    result = ''
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def extract(value, kind):
    match = re.search(r'/spreadsheets/d/([\w-]+)' if kind == 'sheet' else r'/folders/([\w-]+)', value)
    if match:
        return match[1]
    if re.fullmatch(r'[\w-]+', value):
        return value
    raise ValueError('Tautan ' + kind + ' tidak valid.')


