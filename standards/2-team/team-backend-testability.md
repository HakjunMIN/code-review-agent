---
standard_id: team-003
standard_type: team
title: 백엔드팀 표준 - 테스트 가능성 설계
applies_scope: always
tags: ["testability", "dependency-injection", "quality"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: medium
applies_to_globs: ["app/services/**/*.py", "app/routers/**/*.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
리뷰 지적사항을 테스트 케이스로 환원 가능하게 만든다.

## 규칙
- 시간/UUID/외부호출은 주입 가능한 인터페이스 사용.
- 순수 함수 분리를 우선.
- 실패 경로 테스트를 최소 1개 이상 추가.

## 코드 조치 가이드
- 전역 객체 직접 참조를 생성자 주입으로 교체.