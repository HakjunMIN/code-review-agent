---
standard_id: corp-001
standard_type: corporate
title: 전사 표준 - API 입력 검증 및 에러 응답
applies_scope: always
tags: ["validation", "error-handling", "api"]
language: all
updated_at: 2026-02-24
repo: *
team: platform
severity: high
applies_to_globs: ["**/*.py", "**/*.ts"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
외부 입력값을 신뢰하지 않고 검증 실패 시 표준 에러 스키마를 반환한다.

## 규칙
- 모든 API 진입점에서 스키마 검증을 수행한다.
- 에러 응답은 `{code, message, traceId}` 구조를 따른다.
- 내부 예외 메시지를 클라이언트에 그대로 노출하지 않는다.

## 코드 조치 가이드
- `pydantic` 또는 동등한 스키마 검증 도구를 사용한다.
- 에러 핸들러에서 예외를 로깅하고 표준 코드로 매핑한다.