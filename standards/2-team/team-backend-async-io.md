---
standard_id: team-002
standard_type: team
title: 백엔드팀 표준 - 비동기 I/O 처리 원칙
applies_scope: always
tags: ["async", "io", "performance"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/**/*.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
이벤트 루프 블로킹으로 인한 지연을 예방한다.

## 규칙
- async 컨텍스트에서 동기 네트워크 호출 금지.
- CPU 바운드 작업은 별도 워커로 분리.
- 파일 I/O는 비동기 또는 백그라운드 처리.

## 코드 조치 가이드
- `requests` 사용 코드를 `httpx.AsyncClient`로 전환.