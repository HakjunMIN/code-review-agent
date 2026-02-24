---
standard_id: fh-003
standard_type: file_history
title: 파일 조치 이력 - setup_ai_search 재실행 안전성
applies_scope: conditional
tags: ["history", "indexing", "idempotency"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: platform
severity: medium
applies_to_globs: ["scripts/setup_ai_search.py"]
affected_files: ["scripts/setup_ai_search.py"]
related_paths: ["standards/**/*.md"]
postmortem_id: ""
---
# 배경
초기 스크립트는 인덱스 다중 생성/문서 중복 업로드 가능성이 있었다.

## 재발 방지 규칙
- `create_or_update_index` 사용.
- 문서 id는 stable hash 기반으로 생성.

## 코드 조치 가이드
- 청크 단위 ID 생성 규칙을 변경하지 않는다.