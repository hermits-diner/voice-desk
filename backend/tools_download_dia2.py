"""Dia2-2B 가중치 + kyutai/mimi 코덱을 C:\ai\models 아래로 내려받는다."""
import os
import time

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from huggingface_hub import snapshot_download

MAX_TRIES = 8


def dir_size(path: str) -> float:
    if not os.path.isdir(path):
        return 0.0
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(path) for f in fs) / 1024 ** 3


def fetch(repo_id: str, local_dir: str, ignore=None) -> None:
    print(f"\n>>> {repo_id}  ->  {local_dir}", flush=True)
    t0 = time.time()
    for attempt in range(1, MAX_TRIES + 1):
        try:
            snapshot_download(repo_id=repo_id, local_dir=local_dir,
                              ignore_patterns=ignore, max_workers=4)
            break
        except Exception as exc:
            print(f"    [{attempt}/{MAX_TRIES}] {type(exc).__name__}: {exc}", flush=True)
            print(f"    현재 {dir_size(local_dir):.2f} GB 확보, 8초 뒤 이어받기", flush=True)
            if attempt == MAX_TRIES:
                raise
            time.sleep(8)
    print(f"<<< {repo_id}  {dir_size(local_dir):.2f} GB  {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    fetch("nari-labs/Dia2-2B", r"C:\ai\models\Dia2-2B", ignore=["*.gif"])
    fetch("kyutai/mimi", r"C:\ai\models\mimi")
    print("\nDONE")
