---
standard_id: pm-003
standard_type: postmortem
title: 포스트모템 가이드 - 2026-01 리뷰 라인 불일치
applies_scope: conditional
tags: ["postmortem", "diff", "quality"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: medium
applies_to_globs: ["app/services/azure_openai_service.py", "app/utils/diff_parser.py"]
affected_files: ["app/services/azure_openai_service.py", "app/utils/diff_parser.py"]
related_paths: ["app/services/review_service.py"]
postmortem_id: PM-2026-01
---
# 사건 요약
모델이 변경되지 않은 라인에 코멘트를 남겨 개발자 신뢰도가 저하되었다.

## 영향 파일
- app/services/azure_openai_service.py
- app/utils/diff_parser.py

## 코드 조치 가이드
- 리뷰 결과 반환 전 라인 유효성 검증을 강제한다.
- nearest valid line 보정 실패 시 해당 이슈를 제외한다.