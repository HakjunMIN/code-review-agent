---
standard_id: repo-002
standard_type: repository
title: 리포지토리 표준 - Azure AI Search 조회 규약
applies_scope: always
tags: ["azure-ai-search", "rag", "retrieval"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/services/azure_search_service.py", "app/services/review_service.py"]
affected_files: []
related_paths: ["scripts/setup_ai_search.py"]
postmortem_id: ""
---
# 목적
코드 리뷰에 필요한 표준 문서 누락을 방지한다.

## 규칙
- corporate/team/repository 타입은 항상 포함.
- file_history/postmortem 타입은 변경 파일 매칭 시만 포함.
- 검색은 hybrid(BM25+vector)와 semantic config를 사용.

## 코드 조치 가이드
- 변경 파일 목록을 기반으로 필터식을 구성한다.
- 필터 후에도 조건부 문서는 glob 재검증한다.