#!/usr/bin/env python3
"""Fetch raw block data and emit gz + manifest."""
import argparse
import base64
import gzip
import hashlib
import json
import os
import urllib.request

CHAIN = "near"


def get_json(url, timeout=45):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def post_json(url, payload, timeout=45):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.load(r)
    if isinstance(obj, dict) and "error" in obj:
        raise RuntimeError(str(obj["error"]))
    return obj["result"]


def canon(value):
    """Make msgpack-decoded values JSON-safe (bytes -> str/base64)."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"__base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {canon(k) if not isinstance(k, str) else k: canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canon(v) for v in value]
    if isinstance(value, tuple):
        return [canon(v) for v in value]
    return value



RPC = "https://rpc.mainnet.near.org"


def fetch(height):
    block = post_json(RPC, {"jsonrpc": "2.0", "id": 1, "method": "block", "params": {"block_id": height}})
    chunks = []
    tx_count = 0
    for chunk_header in block.get("chunks", []):
        chunk_id = chunk_header["chunk_hash"]
        data = post_json(RPC, {"jsonrpc": "2.0", "id": 1, "method": "chunk", "params": {"chunk_id": chunk_id}})
        txs = data.get("transactions") or []
        tx_count += len(txs)
        chunks.append({"chunk_id": chunk_id, "shard_id": chunk_header.get("shard_id"), "data": data})
    return {"height": height, "block": block, "chunks": chunks, "_tx_count": tx_count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.first < 0 or args.count < 1 or args.count > 100:
        raise SystemExit("invalid first/count")
    first, last = args.first, args.first + args.count - 1
    blocks = []
    tx_count = 0
    for h in range(first, last + 1):
        rec = fetch(h)
        tx_count += rec.pop("_tx_count", 0)
        blocks.append(rec)
    payload = {
        "chain": CHAIN,
        "first": first,
        "last": last,
        "block_count": len(blocks),
        "tx_count": tx_count,
        "blocks": blocks,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    gz_path = args.out + ".gz"
    with gzip.GzipFile(filename=gz_path, mode="wb", mtime=0) as f:
        f.write(raw)
    with open(gz_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    manifest = {
        "first": first,
        "last": last,
        "block_count": len(blocks),
        "tx_count": tx_count,
        "bytes": os.path.getsize(gz_path),
        "sha256": digest,
    }
    with open(args.out + ".manifest.json", "w") as f:
        json.dump(manifest, f, sort_keys=True)
        f.write("\n")
    print("MANIFEST " + json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
