---
standard_id: fh-002
standard_type: file_history
title: 파일 조치 이력 - review_service 검색 쿼리 과다 길이 대응
applies_scope: conditional
tags: ["history", "query", "performance"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: medium
applies_to_globs: ["app/services/review_service.py"]
affected_files: ["app/services/review_service.py"]
related_paths: ["app/services/azure_search_service.py"]
postmortem_id: ""
---
# 배경
대형 PR에서 쿼리 문자열이 과도하게 길어 검색 응답이 불안정했다.

## 재발 방지 규칙
- 쿼리는 2000자 이하로 제한.
- 추가 라인은 상위 50개까지만 반영.

## 코드 조치 가이드
- 검색어 구성과 잘라내기 로직을 `_build_search_query`에 유지.