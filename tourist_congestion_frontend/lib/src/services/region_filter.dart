// Match administrative components, not substrings of street names.
bool matchesRegionPath(String address, String path) {
  if (path.isEmpty) return true;
  final tokens = address.trim().split(RegExp(r'\s+'));
  final selected = path.split('/');
  if (tokens.length < selected.length) return false;
  const aliases = <String, String>{
    '서울': '서울특별시',
    '부산': '부산광역시',
    '대구': '대구광역시',
    '인천': '인천광역시',
    '광주': '광주광역시',
    '대전': '대전광역시',
    '울산': '울산광역시',
    '세종': '세종특별자치시',
    '경기': '경기도',
    '강원': '강원특별자치도',
    '강원도': '강원특별자치도',
    '충북': '충청북도',
    '충남': '충청남도',
    '전북': '전북특별자치도',
    '전라북도': '전북특별자치도',
    '전남': '전라남도',
    '경북': '경상북도',
    '경남': '경상남도',
    '제주': '제주특별자치도',
    '제주도': '제주특별자치도',
  };
  tokens[0] = aliases[tokens[0]] ?? tokens[0];
  selected[0] = aliases[selected[0]] ?? selected[0];
  for (var i = 0; i < selected.length; i++) {
    if (tokens[i] != selected[i]) return false;
  }
  return true;
}
