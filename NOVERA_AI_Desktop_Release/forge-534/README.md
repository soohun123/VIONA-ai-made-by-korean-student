# NOVERA Forge 1.5B · 534 steps

NOVERA AI Desktop 1.2.8의 텍스트 모델용 LoRA입니다. 어댑터는 원본 Qwen2.5-Coder-1.5B-Instruct GGUF와 함께 사용합니다. 호환되는 기반 파일과 어댑터의 SHA-256은 [release.json](release.json)에 있습니다. Qwen의 Apache 2.0 조건과 Forge 수정 사항은 [라이선스](LICENSE-Qwen.txt)와 [고지](NOTICE.txt)를 참조하세요.

| 평가 | Pass@1 또는 정확도 |
|---|---:|
| HumanEval+ | 107/164 (65.24%) |
| HumanEval 기본 | 114/164 (69.51%) |
| MBPP+ | 222/378 (58.73%) |
| 독립 Python 코딩 | 0/12 |
| 로컬 수학 | 0/16 |

코딩 평가는 WASI에서 실행했습니다. 어댑터와 기반 모델의 해시가 일치할 때만 데스크톱에서 로드됩니다.

기존 PyInstaller 배포 폴더와 호환 Qwen 파일이 준비된 경우 [스테이징 스크립트](../stage_forge_release.py)로 Forge 전용 설치 구성을 만들 수 있습니다. 설치기는 어댑터 해시와 데스크톱 버전을 Inno Setup의 Forge 빌드 인수로 받습니다.
