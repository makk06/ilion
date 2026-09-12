"""Address-derived administrative paths; these describe registered places only."""

PROVINCE_ALIASES = {
    '서울': '서울특별시', '부산': '부산광역시', '대구': '대구광역시',
    '인천': '인천광역시', '광주': '광주광역시', '대전': '대전광역시',
    '울산': '울산광역시', '세종': '세종특별자치시', '경기': '경기도',
    '강원': '강원특별자치도', '강원도': '강원특별자치도',
    '충북': '충청북도', '충남': '충청남도',
    '전북': '전북특별자치도', '전라북도': '전북특별자치도', '전남': '전라남도',
    '경북': '경상북도', '경남': '경상남도', '제주': '제주특별자치도', '제주도': '제주특별자치도',
}
PROVINCES = set(PROVINCE_ALIASES.values())


def address_path(address):
    tokens = address.split()
    if not tokens:
        return []
    province = PROVINCE_ALIASES.get(tokens[0], tokens[0])
    if province not in PROVINCES:
        return []
    path = [province]
    if len(tokens) > 1 and tokens[1].endswith(('시', '군', '구')):
        path.append(tokens[1])
        if tokens[1].endswith('시') and len(tokens) > 2 and tokens[2].endswith('구'):
            path.append(tokens[2])
    return path


def parse_region_path(raw):
    tokens = raw.split('/')
    if not 1 <= len(tokens) <= 3 or any(not token or token != token.strip() for token in tokens):
        raise ValueError('region_path must contain 1–3 slash-separated administrative names.')
    tokens[0] = PROVINCE_ALIASES.get(tokens[0], tokens[0])
    if tokens[0] not in PROVINCES:
        raise ValueError('Unknown province in region_path.')
    return tokens


def region_tree(addresses):
    roots = {}
    for address in addresses:
        branch = roots
        path = []
        for token in address_path(address):
            path.append(token)
            node = branch.setdefault(token, {'name': token, 'path': '/'.join(path), 'children': {}})
            branch = node['children']

    def ordered(branch):
        return [{**node, 'children': ordered(node['children'])} for _, node in sorted(branch.items())]
    return ordered(roots)
