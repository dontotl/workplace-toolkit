# Installation / 다른 Codex CLI에서 사용하기

## 1. 스킬 설치

`dontotl/workplace-toolkit`은 private GitHub 저장소입니다. 먼저 저장소 collaborator로 읽기 권한을 부여받고, 그 계정으로 GitHub CLI에 인증해야 합니다.

```bash
gh auth status --hostname github.com
gh repo clone dontotl/workplace-toolkit
cd workplace-toolkit
```

Python 3.11+가 있는 Codex CLI 환경에서 clone한 저장소나 승인된 ZIP을 풀고 `scripts/distribution.py install --dest "$HOME/.agents/skills"`를 실행합니다. 프로젝트 전용은 대상 프로젝트 루트에서 이 스크립트의 절대 경로를 실행하고 `--dest .agents/skills`를 사용합니다.

Windows PowerShell에서는 `python scripts/distribution.py install --dest "$env:USERPROFILE/.agents/skills"`를 사용합니다. 파일 경로는 인수로 전달하며 소스 안에 개인 절대경로를 넣지 않습니다.

`--skill workplace-research --skill ppt-translator`처럼 선택할 수 있습니다. 먼저 `--dry-run`으로 확인하세요. 기존 이름이 있으면 안전하게 중단합니다. 백업·이전은 migration.md를 참고하세요.

Codex의 `$`/`/skills`에서 확인합니다. 자동 발견이 안 되면 새 CLI 세션을 시작합니다. 복사 설치는 시스템 패키지나 커넥터까지 설치하지 않습니다.

## 2. 필요한 의존성만 준비

- 조사/보고: 별도 Python 런타임 불필요(설치기 실행은 Python 사용). 연결된 소스만 사용할 수 있으며, 연결 없는 사용자는 공개 웹/로컬 파일 경로로 시작합니다. 인증된 브라우저 도구가 없으면 SharePoint 자동 다운로드는 사용할 수 없습니다.
- PPT 번역: 사용자 선택 폴더에 가상환경을 만들고 설치된 `ppt-translator/requirements.txt`를 설치합니다. 합성 샘플/테스트에는 requirements-test.txt를 사용합니다. 스크립트는 설치 위치와 무관하게 동작합니다.
- PPT 렌더: 로컬 PowerPoint 또는 LibreOffice, PNG 변환 도구를 준비합니다. 글꼴이 없으면 레이아웃이 달라지므로 대상 언어 글꼴을 확인합니다.
- 발표 제작: 해당 스킬의 의존성 문서를 읽습니다. 모델 가중치·MLX·PyTorch는 설치 준비 단계에서 각 사용자 환경에 맞게 마련합니다. 런타임이 모델을 인터넷에서 자동 다운로드하지 않습니다. Metal은 지원되는 Apple Silicon 환경에서만 선택합니다.

macOS 번역/렌더링을 실측하며, 다른 운영체제의 파일 설치·순수 Python 기능은 별도 검증 범위를 보고합니다. 모든 OS에서 Metal이나 PowerPoint 자동화가 동일하게 동작한다고 보장하지 않습니다.

## 3. 번역 실행

아래 경로는 프로젝트 내 설치 예시입니다. 전역 설치 시 실제 스킬 경로로 바꾸세요.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r .agents/skills/ppt-translator/requirements-test.txt
.venv/bin/python .agents/skills/ppt-translator/examples/make_fixture.py sample.pptx
```

Windows PowerShell에서는 같은 가상환경을 다음처럼 사용합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .agents/skills/ppt-translator/requirements-test.txt
.\.venv\Scripts\python.exe .agents/skills/ppt-translator/examples/make_fixture.py sample.pptx
```

승인된 Codex 세션에 `$ppt-translator sample.pptx를 한국어로 번역하고 검수해줘`라고 요청합니다. 스킬은 로컬 추출 → 현재 세션의 번역문 작성 → 로컬 적용 → 검수로 진행합니다. API 키를 요구하면 구버전 동명 스킬이 선택됐는지 확인하세요.

## 4. 플러그인 배포

루트 `.codex-plugin/plugin.json`은 같은 네 스킬을 묶습니다. 실제 소스 주소는 private 저장소 `https://github.com/dontotl/workplace-toolkit`입니다. 저장소 권한이 없는 사용자에게는 접근되지 않으며, marketplace나 public release에는 등록하지 않았습니다. 지금은 위 standalone 설치 경로를 검증 대상으로 삼고 코드와 스킬을 중복 사본으로 관리하지 않습니다.

## 5. 소스 공유 시 포함/제외

배포 ZIP에는 루트 및 개별 스킬의 MIT LICENSE, 필요한 지침/코드/예시/테스트가 포함됩니다. 예시는 공개 합성 텍스트와 생성 코드입니다. API 키, 계정, 사내 소스맵, 실제 문서, 모델, 실행 환경, 생성 영상은 포함하지 않습니다. 스킬 폴더 하나만 전달할 때도 LICENSE와 필요한 하위 파일을 함께 전달하세요.
