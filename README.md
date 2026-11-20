# VIONA AI / NOVERA AI Desktop

한국 학생이 개발하는 로컬 AI 웹사이트 및 Windows 데스크톱 실행기 소스입니다.

## NOVERA Forge 1.5B · GGUF 다운로드

**[Forge 534스텝 GGUF LoRA 다운로드](https://github.com/soohun123/VIONA-ai-made-by-korean-student/raw/06ffc31a5b0cd9a11c9b5f053eae61c7d0083e69/NOVERA_AI_Desktop_Release/forge-534/NOVERA-Forge-1.5B-LoRA-534steps-f16.gguf)**

호환되는 Qwen2.5-Coder-1.5B-Instruct 기반 GGUF를 먼저 불러온 뒤 이 파일을 LoRA로 적용하세요. HumanEval+ Pass@1은 **65.24% (107/164)**입니다. [기반 모델과 SHA-256](NOVERA_AI_Desktop_Release/forge-534/release.json) · [평가 및 라이선스](NOVERA_AI_Desktop_Release/forge-534/README.md)

- `NovaBrain/NovaBrain_LLM_v8`: 웹 UI, AI 서버, 모델 실행 및 학습 도구 소스
- `NOVERA_AI_Desktop_Release`: 데스크톱 실행기, 테스트, Windows 빌드 및 서명된 로컬 자동 업데이트 도구

## Windows 설치 프로그램

[Setup 다운로드 — Releases](https://github.com/soohun123/VIONA-ai-made-by-korean-student/releases/tag/desktop-v1.2.2-public)

**NOVERA_AI_Setup.exe와 모든 NOVERA_AI_Setup-*.bin 파일을 같은 폴더에 다운로드한 뒤 EXE를 실행하세요.** 파일명을 바꾸지 마세요. `Code → Download ZIP`에는 설치 파일이 포함되지 않습니다.

공개 설치본 1.2.2에는 회원가입·로그인과 Qwen 기반 VIONA AI 1.5B Q4_K_M 채팅 모델이 포함됩니다. 계정은 PC별로 저장됩니다. 추가 학습 LoRA·이미지 모델·소셜 로그인 서비스 설정은 제외했습니다. 개발 PC 전용 자동 업데이트 채널은 공개 설치본에서 비활성화했습니다.

## 배포 범위

이 저장소에는 소스코드와 위 Forge GGUF LoRA 배포본이 있습니다. 공개 Windows 설치 EXE와 해당 설치본의 모델은 위 Releases에서 별도로 제공합니다. 기반 모델 파일, 설치 EXE, 가상환경, 학습 데이터, 대화 기록, API 키, 서명 개인키 및 실제 계정 설정은 Git에 포함하지 않습니다. 모델을 별도로 준비할 때는 해당 제공자의 라이선스를 확인하세요.

## 실행 전 준비

현재 코드는 개발 PC의 기존 모델 경로와 로컬 설정에 연결되어 있습니다. 저장소만 복제해 즉시 실행되는 완전한 설치본은 아닙니다. Python 의존성은 각 requirements 파일을 확인하세요. 데스크톱 빌드 진입점은 `NOVERA_AI_Desktop_Release/build.ps1`이며, `prepare.py`는 기존 프로젝트와 모델이 있는 환경에서 사용하는 준비 도구입니다.

`assets/developer-account.json`, `assets/model-sources.json`, `assets/website-source.json`, `assets/update-channel.json` 등 PC별 설정은 공개하지 않았습니다. 실행 전 자신의 환경에 맞게 준비해야 합니다. 실제 비밀번호 해시나 API 키를 저장소에 추가하지 마세요.

자동 업데이트는 동일 PC의 로컬 게시 폴더를 사용하는 방식입니다. 공개 인터넷 업데이트 서비스는 포함하지 않습니다. 서명 개인키를 새로 만들거나 교체하기 전에 기존 설치 앱의 신뢰 설정을 확인하세요.

## 주의

AI가 생성한 코드와 학습·평가 스크립트를 실행하기 전에 내용을 검토하고 격리된 환경을 사용하세요. 제3자 모델과 라이브러리는 각각의 라이선스를 따릅니다.

## 라이선스 및 무단 재배포 금지

Copyright © 2026 soohun123. All rights reserved.

권리자가 권리를 보유한 본 프로젝트의 원본 코드 및 자산은 **사전 서면 허락 없는 복제·수정·재배포·판매를 금지**합니다. 출처를 표시해도 재배포가 허용되지 않으며, 비영리 재배포에도 허락이 필요합니다. 이 프로젝트는 오픈소스 라이선스로 배포되지 않습니다.

법률이나 GitHub 약관이 허용하는 열람·포크 등의 권리와 제3자 라이선스에 따른 권리는 유지됩니다. 외부 라이브러리와 모델에는 각각의 라이선스가 적용됩니다. 자세한 조건과 허락 요청 방법은 [LICENSE](LICENSE)를 확인하세요.
