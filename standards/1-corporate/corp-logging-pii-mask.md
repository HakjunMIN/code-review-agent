---
standard_id: corp-002
standard_type: corporate
title: 전사 표준 - 로깅 시 민감정보 마스킹
applies_scope: always
tags: ["logging", "security", "pii"]
language: all
updated_at: 2026-02-24
repo: *
team: security
severity: critical
applies_to_globs: ["**/*"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
로그 유출 사고를 방지하기 위해 PII 및 비밀값은 저장하지 않는다.

## 규칙
- 토큰, 비밀번호, 전화번호, 이메일은 원문 로깅 금지.
- 요청/응답 바디 로깅은 allow-list 필드만 허용.
- 운영 로그는 마스킹 유틸 경유 후 기록.

## 코드 조치 가이드
- 공용 `mask_sensitive()` 유틸을 사용한다.
- 로거 호출 전에 구조화 필드 필터를 적용한다.