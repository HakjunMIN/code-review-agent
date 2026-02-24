---
standard_id: repo-001
standard_type: repository
title: 리포지토리 표준 - 환경변수 설정 검증
applies_scope: always
tags: ["config", "env", "validation"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/config.py", "**/*.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
실행환경 차이로 인한 장애를 예방한다.

## 규칙
- 필수 환경변수 누락 시 시작 단계에서 실패.
- 기본값은 안전한 값만 허용.
- 환경변수명 변경 시 README 동시 갱신.

## 코드 조치 가이드
- `BaseSettings` 필수 필드를 명시하고 타입을 엄격히 유지.