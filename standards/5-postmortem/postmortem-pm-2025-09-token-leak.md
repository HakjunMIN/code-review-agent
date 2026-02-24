---
standard_id: pm-001
standard_type: postmortem
title: 포스트모템 가이드 - 2025-09 토큰 노출 사고
applies_scope: conditional
tags: ["postmortem", "security", "token"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: security
severity: critical
applies_to_globs: ["app/services/**/*.py", "app/routers/**/*.py"]
affected_files: ["app/services/github_service.py", "app/services/azure_openai_service.py"]
related_paths: ["app/services/review_service.py"]
postmortem_id: PM-2025-09
---
# 사건 요약
운영 로그에 액세스 토큰 일부가 기록되어 보안 사고가 발생했다.

## 영향 파일
- app/services/github_service.py
- app/services/azure_openai_service.py

## 코드 조치 가이드
- Authorization 헤더/토큰류는 로깅 전에 제거.
- 예외 메시지에도 credential 문자열 포함 금지.