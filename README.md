# VIONA AI / NOVERA AI Desktop

한국 학생이 개발하는 로컬 AI 웹사이트 및 Windows 데스크톱 실행기 소스입니다.

- `NovaBrain/NovaBrain_LLM_v8`: 웹 UI, AI 서버, 모델 실행 및 학습 도구 소스
- `NOVERA_AI_Desktop_Release`: 데스크톱 실행기, 테스트, Windows 빌드 및 서명된 로컬 자동 업데이트 도구

## 배포 범위

이 저장소는 소스코드 배포본입니다. 모델 가중치, LoRA, 설치 EXE, 가상환경, 학습 데이터, 대화 기록, API 키, 서명 개인키 및 실제 계정 설정은 포함하지 않습니다. 모델은 해당 제공자의 라이선스를 확인하고 별도로 준비해야 합니다.

## 실행 전 준비

현재 코드는 개발 PC의 기존 모델 경로와 로컬 설정에 연결되어 있습니다. 저장소만 복제해 즉시 실행되는 완전한 설치본은 아닙니다. Python 의존성은 각 requirements 파일을 확인하세요. 데스크톱 빌드 진입점은 `NOVERA_AI_Desktop_Release/build.ps1`이며, `prepare.py`는 기존 프로젝트와 모델이 있는 환경에서 사용하는 준비 도구입니다.

`assets/developer-account.json`, `assets/model-sources.json`, `assets/website-source.json`, `assets/update-channel.json` 등 PC별 설정은 공개하지 않았습니다. 실행 전 자신의 환경에 맞게 준비해야 합니다. 실제 비밀번호 해시나 API 키를 저장소에 추가하지 마세요.

자동 업데이트는 동일 PC의 로컬 게시 폴더를 사용하는 방식입니다. 공개 인터넷 업데이트 서비스는 포함하지 않습니다. 서명 개인키를 새로 만들거나 교체하기 전에 기존 설치 앱의 신뢰 설정을 확인하세요.

## 주의

AI가 생성한 코드와 학습·평가 스크립트를 실행하기 전에 내용을 검토하고 격리된 환경을 사용하세요. 제3자 모델과 라이브러리는 각각의 라이선스를 따릅니다.
