import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'api_client.dart';

/// 약관·처리방침은 API 서버가 같은 도메인의 `/terms`, `/privacy` 에서 제공한다.
Uri legalPageUri(String path) =>
    Uri.parse(ApiClient.instance.baseUrl).resolve(path);

Future<void> openLegalPage(BuildContext context, String path) async {
  try {
    if (!await launchUrl(legalPageUri(path),
        mode: LaunchMode.externalApplication)) {
      throw Exception('launch failed');
    }
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('페이지를 열지 못했어요. 잠시 후 다시 시도해 주세요.')));
    }
  }
}
