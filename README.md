# Workplace Toolkit

Codex CLI에서 공유·재사용하는 업무 스킬 4종입니다. **개인 경로·API 키·사내 주소를 복사하지 않고**, 각 사용자의 승인된 Codex 환경과 로컬 도구를 사용합니다.

| 스킬 | 역할 | 필요한 것 |
|---|---|---|
| `workplace-research` | 웹·Slack·Outlook·SharePoint·OneDrive 조사와 요청된 다운로드 | 사용자에게 연결된 검색·브라우저 도구 |
| `ppt-translator` | 현재 Codex가 번역, 로컬 코드가 PPT 반영·검증 | Python 3.11+, lxml; 화면 검수용 Office/LibreOffice |
| `visit-call-report` | 메모·선택한 이력에서 한국어 보고서 생성 | 메모, 선택형 JSON/CSV 또는 보고서 사이트 |
| `presentation-studio` | 스토리·대본·발표 노트, 로컬 음성·자막·영상 | 단계별 선택 의존성; TTS 모델과 FFmpeg는 별도 준비 |

## 다른 Codex CLI에 설치

소스는 [private GitHub 저장소](https://github.com/dontotl/workplace-toolkit)에 배포됩니다. 해당 저장소에 읽기 권한이 있는 collaborator만 인증한 GitHub 계정으로 받을 수 있으며, public release나 marketplace 배포가 아닙니다.

```bash
gh auth status --hostname github.com
gh repo clone dontotl/workplace-toolkit
cd workplace-toolkit
```

저장소를 clone하거나 승인된 배포 ZIP을 풀고 루트에서 실행합니다. 기존 스킬은 덮어쓰지 않습니다.

```bash
python3 scripts/distribution.py install --dest "$HOME/.agents/skills" --dry-run
python3 scripts/distribution.py install --dest "$HOME/.agents/skills"
```

필요한 스킬만 설치하려면 `--skill ppt-translator`처럼 지정합니다. 프로젝트 전용은 `--dest .agents/skills`를 사용합니다. CLI에서 `$` 또는 `/skills`로 확인하고, 목록이 갱신되지 않으면 새 세션을 시작합니다. 이 위치·호출 방식은 [Codex 공식 스킬 문서](https://learn.chatgpt.com/docs/build-skills)에 따릅니다.

**설치기는 코드/지침만 복사합니다.** 패키지·모델 설치, 로그인, 커넥터 연결, Codex 설정 수정은 자동으로 하지 않습니다. 자세한 단계는 [설치 안내](docs/installation.md)를 참고하세요.

## 사용 예

```text
$workplace-research 최근 3개월 자료를 공식 문서와 연결된 Slack/SharePoint에서 조사해줘. 다운로드는 하지 마.
$ppt-translator 이 PPTX를 한국어로 번역해줘. 현재 승인된 Codex에서 번역하고, 원본은 보존해줘.
$visit-call-report 이 메모와 지정한 history.json으로 방문보고를 작성해줘. 보고서 사이트에는 접근하지 마.
$presentation-studio PPT 발표자 노트를 그대로 읽는 한국어 음성 영상을 만들어줘. 모델과 작업 경로는 내가 지정할게.
```

## 처리 경계

기본 업무 흐름은 **Enterprise Codex + 로컬 제작**입니다. Codex에서 읽는 내용은 모델 처리 대상이며 완전 오프라인이 아닙니다. 회사가 승인한 워크스페이스와 자료 등급인지 확인하세요. 외부 처리 금지 자료는 별도 `local-only` 흐름을 사용하며, 원문을 원격 Codex에 읽히지 않습니다. 번역기 자체에는 별도 유료 API 호출·인증정보 조회가 없습니다. [보안 안내](docs/security.md)

## 테스트와 배포 준비

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s skills/ppt-translator/tests -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s skills/presentation-studio/tests -v
python3 scripts/distribution.py scan
python3 scripts/distribution.py archive dist/workplace-toolkit-0.1.0-private-ready.zip
```

테스트 샘플은 코드로 생성합니다. 고객 자료·영상·모델은 소스 ZIP에 포함되지 않습니다. 상세 결과·한계는 [검증 보고서](docs/verification.md), 이전 설치본 정리는 [이전 안내](docs/migration.md)를 참고하세요.

라이선스는 **MIT**입니다. 루트와 각 독립 스킬에 LICENSE가 포함됩니다. 저작권·라이선스 표시를 유지해 사용·수정·재배포할 수 있습니다. 별도 의존성과 모델의 라이선스는 각각 적용됩니다. GitHub 배포는 private 접근 제어를 사용하며, 공개 링크·public release·marketplace 등록은 제공하지 않습니다.
