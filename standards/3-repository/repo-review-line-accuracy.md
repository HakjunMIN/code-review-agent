---
standard_id: repo-003
standard_type: repository
title: 리포지토리 표준 - 리뷰 코멘트 라인 정확도
applies_scope: always
tags: ["review", "diff", "line-number"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: medium
applies_to_globs: ["app/services/azure_openai_service.py", "app/utils/diff_parser.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
# 목적
리뷰 코멘트가 실제 변경 라인과 불일치하는 문제를 방지한다.

## 규칙
- 코멘트 라인은 diff의 '+' 라인에만 허용.
- 유효하지 않은 라인은 가장 가까운 변경 라인으로 보정.

## 코드 조치 가이드
- 라인 검증 함수를 공통 유틸로 사용하고 우회 금지.