# Plan: FastAPI Code Review Agent for GitHub PRs

GitHub PR의 코드 변경사항을 Azure OpenAI로 분석하여 자동 리뷰를 수행하고, 리뷰 결과를 PR 코멘트 및 인라인 제안으로 남기는 FastAPI 기반 에이전트를 구축합니다.

## Steps

1. **프로젝트 구조 생성**: FastAPI 앱 구조 설정 - `app/main.py`, `services/`, `routers/`, `models/` 디렉토리와 , `.env.example` 파일 생성, uv 프로젝트로 관리해야함. 

2. **GitHub Service 구현**: `app/services/github_service.py`에 PR 정보 조회(`/pulls/{pr_number}`), 변경 파일 목록 조회(`/pulls/{pr_number}/files`), 파일 내용 다운로드, 리뷰 및 인라인 코멘트 포스팅 기능 구현

3. **Azure OpenAI Service 구현**: `app/services/azure_openai_service.py`에 코드 분석 및 리뷰 생성 로직 구현 - 파일별 diff와 컨텍스트를 분석하여 이슈, 제안사항, 심각도를 JSON 형태로 반환

4. **Review Orchestration 구현**: `app/services/review_service.py`에서 GitHub → Azure OpenAI → GitHub 코멘트 포스팅까지의 전체 워크플로우 조율

5. **FastAPI 엔드포인트 구현**: `POST /review` 엔드포인트 - PR URL과 GitHub PAT를 받아 리뷰 수행 후 결과 반환, `POST /webhook` 엔드포인트 - GitHub Webhook으로 자동 트리거 지원 (선택사항)

6. **Prompt Engineering**: 코드 리뷰 전문 시스템 프롬프트 작성 - 이슈 분류(버그/보안/성능/스타일), 라인 번호 지정, 수정 제안 코드 포함

## Further Considerations

1. **Webhook vs API 호출 방식?** PR 생성 시 자동 트리거(Webhook) / 수동 API 호출 / 둘 다 지원 - 어떤 방식을 선호하시나요? -> 둘다지원할것

2. **리뷰 결과 형식?** GitHub Review(`APPROVE`/`REQUEST_CHANGES`/`COMMENT`) 사용 / 단순 코멘트만 / 인라인 제안(suggestion block) 포함 - 모두 지원할까요? -> 모두 지원

3. **대용량 PR 처리?** 변경 파일이 많을 경우 파일별 개별 분석 / 전체 통합 분석 / 중요 파일만 필터링 - 어떤 전략을 사용할까요? 개별분석
