import 'package:flutter/material.dart';

class CrowdBadge extends StatelessWidget {
  const CrowdBadge({
    super.key,
    required this.label,
    required this.color,
  }) : compact = false;

  const CrowdBadge.compact({
    super.key,
    required this.label,
    required this.color,
  }) : compact = true;

  final String label;
  final Color color;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 6 : 9,
        vertical: compact ? 3 : 5,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: compact ? 5 : 7,
            height: compact ? 5 : 7,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          SizedBox(width: compact ? 3 : 5),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: compact ? 9 : 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}
