import 'package:flutter/material.dart';

import '../models/place.dart';

const mockPlaces = <Place>[
  Place(
    name: '서울숲',
    area: '서울 성동구',
    category: '자연 · 공원',
    crowdLevel: CrowdLevel.low,
    crowdText: '여유',
    distance: '1.2km',
    icon: Icons.park_rounded,
    description: '산책하기 좋은 시간이에요. 현재 방문객이 비교적 적어요.',
  ),
  Place(
    name: '성수동 카페거리',
    area: '서울 성동구',
    category: '음식 · 카페',
    crowdLevel: CrowdLevel.medium,
    crowdText: '보통',
    distance: '1.8km',
    icon: Icons.local_cafe_rounded,
    description: '일부 매장에 대기가 있지만 이동은 원활한 편이에요.',
  ),
  Place(
    name: '경복궁',
    area: '서울 종로구',
    category: '역사 · 문화',
    crowdLevel: CrowdLevel.high,
    crowdText: '혼잡',
    distance: '4.6km',
    icon: Icons.account_balance_rounded,
    description: '현재 방문객이 많아요. 한 시간 뒤 방문을 추천해요.',
  ),
];
