"""VibeVoice-1.5B 가중치 + Qwen2.5-1.5B 토크나이저를 C:\ai\models 아래로 내려받는다.

HF 다운로드는 대용량 샤드에서 연결이 끊기는 일이 흔하므로 재시도로 감싼다.
snapshot_download 는 .incomplete 파일을 보고 이어받는다.
"""
import os
import time

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from huggingface_hub import snapshot_download

MAX_TRIES = 8


def dir_size(path: str) -> float:
    if not os.path.isdir(path):
        return 0.0
    return sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, fs in os.walk(path)
        for f in fs
    ) / 1024 ** 3


def fetch(repo_id: str, local_dir: str, allow=None, ignore=None) -> None:
    print(f"\n>>> {repo_id}  ->  {local_dir}", flush=True)
    t0 = time.time()
    for attempt in range(1, MAX_TRIES + 1):
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                allow_patterns=allow,
                ignore_patterns=ignore,
                max_workers=4,
            )
            break
        except Exception as exc:  # 연결 끊김 등
            got = dir_size(local_dir)
            print(f"    [{attempt}/{MAX_TRIES}] {type(exc).__name__}: {exc}", flush=True)
            print(f"    현재 {got:.2f} GB 확보, 8초 뒤 이어받기", flush=True)
            if attempt == MAX_TRIES:
                raise
            time.sleep(8)
    print(f"<<< {repo_id}  {dir_size(local_dir):.2f} GB  {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    fetch(
        "microsoft/VibeVoice-1.5B",
        r"C:\ai\models\VibeVoice-1.5B",
        ignore=["figures/*", "*.png"],
    )
    # VibeVoiceProcessor 가 preprocessor_config.json 의
    # language_model_pretrained_name 을 보고 Qwen2.5 토크나이저를 찾는다.
    fetch(
        "Qwen/Qwen2.5-1.5B",
        r"C:\ai\models\Qwen2.5-1.5B",
        allow=[
            "tokenizer.json", "tokenizer_config.json", "vocab.json",
            "merges.txt", "special_tokens_map.json", "config.json",
            "generation_config.json",
        ],
    )
    print("\nDONE")
