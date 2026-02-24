---
standard_id: team-001
standard_type: team
title: 백엔드팀 표준 - FastAPI 라우터/서비스 분리
applies_scope: always
tags: ["fastapi", "architecture", "layering"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: medium
applies_to_globs: ["app/routers/**/*.py", "app/services/**/*.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
프레젠테이션/비즈니스 로직 결합을 줄여 테스트 용이성을 높인다.

## 규칙
- 라우터는 입력 검증/응답 변환만 담당.
- 비즈니스 로직은 서비스 계층으로 이동.
- 외부 API 클라이언트는 서비스 의존성으로 주입.

## 코드 조치 가이드
- 라우터 함수 내 복잡한 분기/반복을 서비스 메서드로 이동.