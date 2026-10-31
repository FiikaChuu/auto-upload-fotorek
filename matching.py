import re

def number(value):
    match = re.match(r'^(\d+)(?=$|[\s._-])', str(value).strip())
    return int(match[1]) if match else None


ALIASES = {'no': {'no', 'nomor', 'number'}, 'pic': {'pic', 'penanggungjawab'},
           'link': {'linkdrive', 'linkgoogledrive', 'tautandrive'}}


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def parse_columns(values):
    result = {}
    for name in ALIASES:
        value = str(values.get(name, '')).strip().upper()
        if not re.fullmatch('[A-Z]{1,3}', value):
            raise ValueError('Kolom harus huruf seperti A, D, atau G.')
        index = 0
        for char in value:
            index = index * 26 + ord(char) - 64
        result[name] = index - 1
    if len(set(result.values())) != 3:
        raise ValueError('Kolom No., PIC, dan Link Drive harus berbeda.')
    return result


def detect(rows, columns=None):
    if columns is not None:
        if set(columns) != set(ALIASES) or any(type(i) is not int or i < 0 for i in columns.values()) or len(set(columns.values())) != 3:
            raise ValueError('Pengaturan kolom tidak valid.')
        for index, row in enumerate(rows):
            if all(col < len(row) and normalized(row[col]) in ALIASES[name] for name, col in columns.items()):
                return index, dict(columns)
        expected = ', '.join(f'{name}={column(col)}' for name,col in columns.items())
        raise ValueError(f'Judul kolom tidak cocok dengan pengaturan ({expected}). Periksa huruf kolom di aplikasi atau pilih Deteksi otomatis. Sheets tidak diubah.')
    ambiguous = []
    for index, row in enumerate(rows):
        found = {name: [] for name in ALIASES}
        for col, value in enumerate(row):
            for name, options in ALIASES.items():
                if normalized(value) in options:
                    found[name].append(col)
        # Decorative/partial rows can repeat words without being a header.
        if all(found.values()):
            if all(len(cols) == 1 for cols in found.values()):
                return index, {name: cols[0] for name,cols in found.items()}
            ambiguous.append((index,found))
            break
    if ambiguous:
        index,found = ambiguous[0]
        duplicates = '; '.join(f'{name}: '+', '.join(column(c) for c in cols) for name,cols in found.items() if len(cols) > 1)
        raise ValueError(f'Baris judul {index+1} memiliki beberapa kandidat kolom ({duplicates}). Matikan Deteksi otomatis dan isi kolom tujuan di aplikasi, misalnya No.=A, PIC=D, Link Drive=G. Tidak perlu mengubah Sheets.')
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


