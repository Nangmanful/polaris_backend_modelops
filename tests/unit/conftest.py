"""단위 테스트 공통 설정.

- 레포 루트를 sys.path에 추가해 `modelops` 패키지를 import 가능하게 한다.
- 모든 테스트는 네트워크·DB 없이 결정론적으로 동작해야 한다.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
