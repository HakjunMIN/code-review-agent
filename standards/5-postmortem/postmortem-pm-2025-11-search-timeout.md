---
standard_id: pm-002
standard_type: postmortem
title: 포스트모템 가이드 - 2025-11 검색 타임아웃 장애
applies_scope: conditional
tags: ["postmortem", "timeout", "search"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/services/azure_search_service.py", "scripts/setup_ai_search.py"]
affected_files: ["app/services/azure_search_service.py"]
related_paths: ["app/config.py"]
postmortem_id: PM-2025-11
---
# 사건 요약
검색 요청이 장시간 블로킹되며 리뷰 파이프라인이 지연되었다.

## 영향 파일
- app/services/azure_search_service.py

## 코드 조치 가이드
- 검색 상한 건수와 max chars를 명시적으로 제한.
- 쿼리 길이 절단 정책을 유지하고 무제한 확장 금지.