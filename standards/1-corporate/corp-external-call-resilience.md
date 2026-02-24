---
standard_id: corp-003
standard_type: corporate
title: 전사 표준 - 외부 연동 호출 복원력
applies_scope: always
tags: ["resilience", "retry", "timeout"]
language: all
updated_at: 2026-02-24
repo: *
team: architecture
severity: high
applies_to_globs: ["**/*.py", "**/*.ts", "**/*.js"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
외부 서비스 장애 전파를 차단한다.

## 규칙
- timeout 없는 외부 호출 금지.
- 지수 백오프 재시도는 최대 3회.
- 회로차단기 또는 fallback 경로를 제공.

## 코드 조치 가이드
- SDK 기본 timeout을 명시적으로 override.
- 재시도 대상 예외를 화이트리스트로 제한.