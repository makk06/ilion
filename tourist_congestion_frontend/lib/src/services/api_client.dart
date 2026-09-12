import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

/// Shared transport. Retries only after a rejected access token; never retries
/// a timed-out write, whose outcome may already have been committed by server.
class ApiClient {
  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = (baseUrl ??
                const String.fromEnvironment('API_BASE_URL',
                    defaultValue: 'http://127.0.0.1:8000/api'))
            .replaceFirst(RegExp(r'/+$'), '');

  static ApiClient instance = ApiClient();
  final http.Client _client;
  final String baseUrl;
  String? accessToken;
  Future<bool> Function()? refreshAccessToken;
  Future<bool>? _refreshing;

  Uri _uri(String path, Map<String, String>? query) =>
      Uri.parse('$baseUrl/${path.replaceFirst(RegExp(r'^/+'), '')}')
          .replace(queryParameters: query);

  String mediaUrl(String path) => Uri.parse(baseUrl).resolve(path).toString();

  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      _request('GET', path, query: query);
  Future<dynamic> post(String path, {Object? body}) =>
      _request('POST', path, body: body);
  Future<dynamic> patch(String path, {Object? body}) =>
      _request('PATCH', path, body: body);
  Future<dynamic> delete(String path) => _request('DELETE', path);

  Future<bool> _refresh() async {
    final callback = refreshAccessToken;
    if (callback == null) return false;
    final pending = _refreshing;
    if (pending != null) return pending;
    final next = callback();
    _refreshing = next;
    try {
      return await next;
    } finally {
      _refreshing = null;
    }
  }

  Future<dynamic> _request(String method, String path,
      {Map<String, String>? query, Object? body, bool retry = true}) async {
    try {
      final request = http.Request(method, _uri(path, query));
      request.headers['Accept'] = 'application/json';
      if (accessToken != null) {
        request.headers['Authorization'] = 'Bearer $accessToken';
      }
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final response = await http.Response.fromStream(
              await _client.send(request).timeout(const Duration(seconds: 20)))
          .timeout(const Duration(seconds: 20));
      if (response.statusCode == 401 &&
          retry &&
          !path.startsWith('/auth/') &&
          await _refresh()) {
        return _request(method, path, query: query, body: body, retry: false);
      }
      return _decode(response);
    } on TimeoutException {
      throw const ApiException('서버 응답이 지연되고 있어요. 등록 작업은 목록을 확인한 뒤 다시 시도해 주세요.');
    } on http.ClientException {
      throw const ApiException('서버에 연결할 수 없어요. 네트워크 연결을 확인하고 다시 시도해 주세요.');
    }
  }

  Future<dynamic> upload(String path,
      {required Map<String, String> fields,
      required Uint8List bytes,
      required String filename,
      String method = 'POST',
      bool retry = true}) async {
    try {
      final request = http.MultipartRequest(method, _uri(path, null));
      request.fields.addAll(fields);
      if (accessToken != null) {
        request.headers['Authorization'] = 'Bearer $accessToken';
      }
      request.files.add(
          http.MultipartFile.fromBytes('photo', bytes, filename: filename));
      final response = await http.Response.fromStream(
              await _client.send(request).timeout(const Duration(seconds: 40)))
          .timeout(const Duration(seconds: 40));
      if (response.statusCode == 401 && retry && await _refresh()) {
        return upload(path,
            fields: fields,
            bytes: bytes,
            filename: filename,
            method: method,
            retry: false);
      }
      return _decode(response);
    } on TimeoutException {
      throw const ApiException('사진 전송이 지연되고 있어요. 등록 여부를 먼저 확인해 주세요.');
    } on http.ClientException {
      throw const ApiException('사진을 전송하지 못했어요. 네트워크 연결을 확인해 주세요.');
    }
  }

  dynamic _decode(http.Response response) {
    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw ApiException('서버 응답을 읽지 못했어요. 잠시 후 다시 시도해 주세요.',
          statusCode: response.statusCode);
    }
    if (response.statusCode < 200 ||
        response.statusCode >= 300 ||
        decoded is! Map ||
        decoded['success'] != true) {
      final message = decoded is Map
          ? (decoded['message'] ?? decoded['detail'] ?? decoded)
          : null;
      throw ApiException(_message(message, response.statusCode),
          statusCode: response.statusCode);
    }
    return decoded['data'];
  }

  String _message(dynamic value, int status) {
    if (value is String && value.isNotEmpty) return value;
    if (value is Map) {
      return value.entries
          .map((e) =>
              '${e.key}: ${e.value is List ? (e.value as List).join(', ') : e.value}')
          .join('\n');
    }
    if (status == 401) return '로그인이 필요하거나 만료되었어요. 다시 로그인해 주세요.';
    return '요청을 처리하지 못했어요. 다시 시도해 주세요.';
  }
}
