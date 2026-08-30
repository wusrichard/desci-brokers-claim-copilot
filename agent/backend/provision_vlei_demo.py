"""Idempotently provision the demo vLEI identities used by the web app.

The sandbox state contains private key seeds and remains under vlei-sandbox/.vlei,
which is git-ignored.  Application code only discovers the resulting SAIDs at
runtime; no credential identifier or private key is committed.
"""

import json
import os
import subprocess


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.normpath(os.path.join(HERE, "..", ".."))
SANDBOX_DIR = os.environ.get("VLEI_SANDBOX_DIR") or os.path.join(PROJECT_DIR, "vlei-sandbox")
CLI = os.path.join(SANDBOX_DIR, "scripts", "vlei_sandbox.py")
STATE_PATH = os.path.join(SANDBOX_DIR, ".vlei", "state.json")

AGENCY_LEI = "8945002HONGTAI00TW15"
EMPLOYER_LEI = "8945004JINGHONG0TW26"


def _run(*args):
    proc = subprocess.run(
        ["python3", CLI, *args], cwd=SANDBOX_DIR, capture_output=True, text=True
    )
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def _load():
    with open(STATE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _find(state, cred_type, lei=None, person=None):
    for said, entry in state.get("credentials", {}).items():
        if entry.get("type") != cred_type:
            continue
        attrs = entry.get("acdc", {}).get("a", {})
        if lei is not None and attrs.get("LEI") != lei:
            continue
        if person is not None and attrs.get("personLegalName") != person:
            continue
        return said, entry
    return None, None


def _is_revoked(state, said, entry):
    actor = state.get("actors", {}).get(entry.get("issuer"), {})
    registry = actor.get("registries", {}).get(entry.get("registry"), {})
    return any(event.get("t") == "rev" for event in registry.get("tel", {}).get(said, []))


def _ensure_actor(state, alias, registry=None):
    if alias in state.get("actors", {}):
        return
    args = ["actor", "add", "--alias", alias]
    if registry:
        args += ["--registry", registry]
    _run(*args)


def main():
    if not os.path.isfile(CLI):
        print("vLEI demo provisioning skipped: sandbox CLI not found")
        return False

    # A clean checkout has no private sandbox state. Build the original agency
    # chain first, then extend the same pinned-root ecosystem with the employer.
    if not os.path.isfile(STATE_PATH):
        _run(
            "demo", "--lei", AGENCY_LEI, "--person", "陳美玲",
            "--role", "Chief Executive Officer", "--context-role", "理賠承辦人",
        )

    state = _load()
    qvi_said, _ = _find(state, "qvi")
    agency_le_said, _ = _find(state, "le", lei=AGENCY_LEI)
    if not qvi_said or not agency_le_said:
        raise RuntimeError("sandbox 缺少既有 QVI／仲介 LE 信任鏈，請重建 demo state")

    # Preserve the existing revoked-officer demonstration on a clean checkout.
    _ensure_actor(state, "former_officer")
    state = _load()
    former_said, former_entry = _find(state, "ecr", lei=AGENCY_LEI, person="林志豪")
    if not former_said:
        _run(
            "issue", "--type", "ecr", "--issuer", "le", "--holder", "former_officer",
            "--lei", AGENCY_LEI, "--person", "林志豪", "--context-role", "理賠承辦人",
            "--auth", agency_le_said,
        )
        state = _load()
        former_said, former_entry = _find(state, "ecr", lei=AGENCY_LEI, person="林志豪")
    if former_said and not _is_revoked(state, former_said, former_entry):
        _run("revoke", "--said", former_said)

    # Employer chain: QVI -> Jinghong Legal Entity -> Taka ECR.
    state = _load()
    _ensure_actor(state, "employer", "employerRegistry")
    state = _load()
    _ensure_actor(state, "taka")
    state = _load()

    employer_le_said, _ = _find(state, "le", lei=EMPLOYER_LEI)
    if not employer_le_said:
        _run(
            "issue", "--type", "le", "--issuer", "qvi", "--holder", "employer",
            "--lei", EMPLOYER_LEI, "--auth", qvi_said,
        )
        state = _load()
        employer_le_said, _ = _find(state, "le", lei=EMPLOYER_LEI)

    taka_said, _ = _find(state, "ecr", lei=EMPLOYER_LEI, person="Taka")
    if not taka_said:
        _run(
            "issue", "--type", "ecr", "--issuer", "employer", "--holder", "taka",
            "--lei", EMPLOYER_LEI, "--person", "Taka",
            "--context-role", "Migrant Worker Manager", "--auth", employer_le_said,
        )
        state = _load()
        taka_said, _ = _find(state, "ecr", lei=EMPLOYER_LEI, person="Taka")

    print("vLEI demo identities ready: Taka ECR {}…".format(taka_said[:12]))
    return True


if __name__ == "__main__":
    main()
