---
standard_id: fh-001
standard_type: file_history
title: 파일 조치 이력 - azure_search_service 조건부 필터 누락 수정
applies_scope: conditional
tags: ["history", "azure-search", "filter"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/services/azure_search_service.py"]
affected_files: ["app/services/azure_search_service.py"]
related_paths: ["app/services/review_service.py"]
postmortem_id: ""
---
# 배경
과거에 조건부 표준(4,5)이 무조건 참조되어 false positive 리뷰가 증가했다.

## 재발 방지 규칙
- 조건부 표준은 변경 파일 매칭 후에만 prompt에 주입.
- 필터 조건이 넓을 경우 post-filter로 재검증.

## 코드 조치 가이드
- `standard_type` 별 분기와 매칭 함수를 분리 유지한다.