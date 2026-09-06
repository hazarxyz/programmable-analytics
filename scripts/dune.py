#!/usr/bin/env python3
"""Version existing public Dune queries without executing them."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.dune.com/api/v1/query/"


def normalized(sql):
    return sql.replace("\r\n", "\n").strip()


def digest(sql):
    return hashlib.sha256(normalized(sql).encode()).hexdigest()


def read_config():
    config = json.loads((ROOT / "dune.json").read_text())
    if not config.get("owner") or not config.get("queries"):
        raise ValueError("The owner and managed queries are required.")
    seen = set()
    for query in config["queries"]:
        query_id = query["id"]
        if type(query_id) is not int or query_id <= 0 or query_id in seen:
            raise ValueError("Query IDs must be unique positive integers.")
        seen.add(query_id)
        path = (ROOT / query["file"]).resolve()
        if not path.is_relative_to(ROOT / "queries") or path.suffix != ".sql":
            raise ValueError("Query files must be SQL files inside queries/.")
        if not normalized(path.read_text()):
            raise ValueError(f"Query {query_id} is empty.")
    for card in config["dashboard"]["cards"]:
        if card["query_id"] not in seen:
            raise ValueError("A dashboard card references an unmanaged query.")
    return config


def request(query_id, payload=None):
    key = os.environ.get("DUNE_API_KEY", "").strip()
    if not key:
        raise ValueError("Set DUNE_API_KEY to a key from the programmablehq team.")
    headers = {"X-Dune-Api-Key": key, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    req = Request(API + str(query_id), data=data, headers=headers,
                  method="PATCH" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=45) as response:
            return json.load(response)
    except HTTPError as error:
        # Avoid logging credentials or untrusted response bodies.
        raise RuntimeError(f"Dune API returned HTTP {error.code} for query {query_id}.") from None
    except URLError:
        raise RuntimeError(f"Could not reach Dune for query {query_id}.") from None


def remote_sql(query, owner):
    remote = request(query["id"])
    if remote.get("query_id") != query["id"] or remote.get("owner") != owner:
        raise ValueError("Dune query ID or owner does not match the repository.")
    if any(remote.get(flag) for flag in ("is_private", "is_archived", "is_temp", "is_unsaved")):
        raise ValueError("Only saved, active, public queries can be synchronized.")
    sql = remote.get("query_sql")
    if not isinstance(sql, str) or not normalized(sql):
        raise ValueError("Dune returned an empty or missing query.")
    return sql


def previous_sql(ref, filename):
    if not ref or set(ref) == {"0"}:
        return None
    if len(ref) != 40 or any(c not in "0123456789abcdef" for c in ref):
        raise ValueError("The base revision must be a full commit SHA.")
    result = subprocess.run(["git", "show", f"{ref}:{filename}"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError("Cannot read the previous SQL revision; reconcile changes manually.")
    return result.stdout


def sync(operation, query, owner, base_ref=None):
    path = ROOT / query["file"]
    local = path.read_text()
    current = remote_sql(query, owner)
    if operation == "pull":
        path.write_text(current.rstrip() + "\n")
        print(f"Imported query {query['id']} ({digest(current)}).")
        return
    if digest(current) == digest(local):
        print(f"Verified query {query['id']} ({digest(local)}).")
        return
    if operation == "verify":
        raise ValueError(f"Query {query['id']} differs from Dune. Review or pull the current SQL.")
    if base_ref is not None:
        previous = previous_sql(base_ref, query["file"])
        if previous is None or digest(previous) != digest(current):
            raise ValueError("Dune SQL changed outside this revision. Pull and reconcile it first.")
    result = request(query["id"], {"query_sql": local})
    if result.get("query_id") != query["id"]:
        raise ValueError("Dune did not confirm the expected query ID.")
    if digest(remote_sql(query, owner)) != digest(local):
        raise ValueError("Dune readback does not match the published SQL.")
    print(f"Published and verified query {query['id']} ({digest(local)}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "verify", "pull", "push"))
    parser.add_argument("--base-ref", help="Previous commit SHA for an automatic push.")
    args = parser.parse_args()
    try:
        config = read_config()
        if args.operation == "check":
            print(f"Valid configuration: {len(config['queries'])} query, "
                  f"{len(config['dashboard']['cards'])} dashboard cards.")
            return
        for query in config["queries"]:
            sync(args.operation, query, config["owner"], args.base_ref)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
