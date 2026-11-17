# 보안 정책 / Security policy

보안 취약점을 발견하셨다면 **공개 이슈 대신** 이 레포의 **Security → Report a vulnerability**(비공개 취약점 신고)로 알려 주세요. 확인 후 답변드리고, 고친 버전을 릴리스하면서 함께 안내합니다.

If you find a security issue, please **do not open a public issue**. Use **Security → Report a vulnerability** in this repository to report it privately. We will reply after checking and announce the fix with a release.

포함된 스크립트는 오프라인으로 동작합니다. CODEOWNERS 파일과 파일 목록만 읽고, 네트워크 연결을 열지 않으며, 사용자가 지정한 `--out` 파일에만 씁니다. / The bundled script runs offline: it reads the CODEOWNERS file and a file list, opens no network connection and writes only the `--out` file you name.
