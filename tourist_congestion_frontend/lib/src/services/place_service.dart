import '../models/place.dart';
import 'api_client.dart';

class PlacePage {
  PlacePage.fromJson(Map<String, dynamic> json)
      : items = (json['items'] as List)
            .map((e) => Place.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        page = (json['pagination']['page'] as num).toInt(),
        totalPages = (json['pagination']['total_pages'] as num).toInt();
  final List<Place> items;
  final int page, totalPages;
  bool get hasMore => page < totalPages;
}

class PlaceService {
  static final instance = PlaceService();
  Future<PlacePage> list(
          {String keyword = '',
          String regionCode = '',
          String regionPath = '',
          String crowdLevel = '',
          int page = 1}) async =>
      PlacePage.fromJson(Map<String, dynamic>.from(
          await ApiClient.instance.get('/places', query: {
        'keyword': keyword,
        'region_code': regionCode,
        'region_path': regionPath,
        'crowd_level': crowdLevel,
        'page': '$page'
      }) as Map));
  Future<Place> detail(int id) async =>
      Place.fromJson(Map<String, dynamic>.from(
          await ApiClient.instance.get('/places/$id') as Map));
  Future<PlacePage> nearby(
          {required double latitude,
          required double longitude,
          String category = '',
          String crowdLevel = '',
          double radiusKm = 10,
          int page = 1}) async =>
      PlacePage.fromJson(Map<String, dynamic>.from(
          await ApiClient.instance.get('/places/nearby', query: {
        'latitude': '$latitude',
        'longitude': '$longitude',
        'category': category,
        'crowd_level': crowdLevel,
        'radius_km': '$radiusKm',
        'page': '$page'
      }) as Map));
}
