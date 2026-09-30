# AGENTS.md

Specifications only. `tools/` holds the gates that check them; `.github/workflows/` runs the same
script. Nothing that implements the specified system belongs here — the code, its tests, its
runbooks, its conformance results and the tracker for work on the code live in
[`douglaz/fedimint-wallets`](https://github.com/douglaz/fedimint-wallets). Work on the
specification itself is tracked in `.beads/` here (`br`, ids `spec-…`); a bead is a work item,
never a requirement, and nothing in `.beads/` is normative.

## The one rule that shapes every edit

This set is **prescriptive** (`ADR-0032`): a requirement states what a compliant wallet MUST,
MUST NOT, SHOULD or MAY do, completely enough that an implementer who has never seen the existing
code can build one, and precisely enough that any implementation can be reviewed against it. It
presupposes the product's stack — Rust, the Fedimint client SDK, its embedded database, the
hosts — and no particular codebase, and it describes no deployment.

The test for a sentence is the **refactor test**: a rewrite of the code that keeps every byte on
disk, every byte on the wire and every observable behaviour identical must not be able to break
it. On-disk shapes, wire shapes, protocol facts and the names of persisted or serialized types
pass. Function and method names, crate and file paths, line numbers, frameworks, dependency pins
and "where in the code this happens" fail, and do not belong in a requirement.

Behaviour the code does not have is not a reason to soften a requirement. It goes in one of two
other places:

- a **product decision nobody has taken** → `11-open-questions.md`, and the set is silent on the
  behaviour until an ADR answers it;
- an **implementation that falls short** → the code repository's `docs/open-findings.md`
  (`Fn` items, one per tracked issue, each a non-conformance against a requirement here).

## Gates

`bash tools/check-all.sh`, before you start and again before you report done. Run it unpiped and
read its exit code — a pipe reports the pipeline's status, not the gate's. Green is evidence
because CI also breaks a document on every run and asserts each gate rejects it.

The codebase-reference gate is a **ratchet**: `tools/codebase-refs-baseline.txt` holds, per
document, the number of lines that still name the codebase, and the gate fails when a document
has more — or fewer, so the baseline is lowered in the same change that earns it. It reached
zero when the review that `ADR-0032` started closed (2026-09-18) and stays there: a new
reference fails the gate.

## Writing a requirement

**State the behaviour, not the mechanism.** A requirement is observable at one of the wallet's
boundaries: what reaches a federation or gateway, what is derived from the seed, what a frontend
sees, what survives a crash. If the only way to check a sentence is to read the code, it is not a
requirement yet.

**Cite the owner.** One rule, one home; everywhere else points at it with the id in backticks.
A second normative copy drifts (`README.md`, *One owner per rule*). Arguments have owners too:
re-explaining a rule elsewhere restates it, and the restatement drifts.

**A decision gets its identifier when it is accepted.** Name the id a change lands on — the
requirement it amends, or the next free number in the right namespace — before writing it, so
"did we apply everything?" is a `grep`. Identifiers are append-only; the conventions are in
`README.md`, *Requirement conventions*.

**Quote, don't characterise.** A sentence about what another requirement says carries that
requirement's words.

**Prefer a scenario to an assertion.** When a requirement can be demonstrated, `10-conformance-checklist.md` carries the scenario that demonstrates it, and the requirement cites it.

## Conventions with a home already

- Identifiers, retention, withdrawn ids → `README.md`, *Requirement conventions*.
- Vocabulary, and which words are banned → `CONTEXT.md`.
- Decisions and what was rejected to reach them → `docs/adr/`.
- What a conformant implementation must demonstrate → `10-conformance-checklist.md`.
- What the existing implementation does not yet do → the code repository's `docs/open-findings.md`.

<!-- agent-discipline-v1 -->
## Working agreement

These rules are here because agents get them wrong by default, not because they
are good general advice.

**Edits must be verified, not assumed.** Prefer your harness's edit tool: it
fails loudly when the target text does not match. `sed -i` and `str.replace()`
do the opposite — a pattern that matches nothing changes nothing, exits 0, and
prints whatever success message you wrote. Batching several edits into one
scripted call is the usual reason this happens, and the saved tool calls are not
worth it. If you do script an edit, assert the target exists before replacing and
make the success message conditional on that assert, then grep the file
afterwards for both the new text and the absence of the old. Prose and markdown
are where this bites hardest: nothing compiles a README, so a silently skipped
edit survives and gets reported as done.

The check does not stop at the file. `nothing to commit, working tree clean` reads
exactly the same whether the work was already committed or was reverted underneath
you by another process holding the tree — so never take that message as proof a
commit happened. Take the exit code instead (`git commit` exits **1** on an empty
commit), and for anything you care about also look inside the commit, since a
partial loss commits cleanly at exit 0:

```
git add -- <every path this change touched>   # not `git add -A`: on a dirty tree it
git diff --cached                            # sweeps in unrelated work — and READ this,
                                             # since staging a path that was already
                                             # dirty takes the other agent's hunks too
git commit -m "<msg>" || { echo "commit produced nothing"; exit 1; }
git show --stat --format= HEAD               # all the paths you meant, and only those
```

Then confirm the *content* landed, per file, by the check that fits it — a file that
gained content must contain a distinctive new phrase; a file you removed lines from must
still exist **and** hold the expected remaining count of the deleted phrase; a deleted path
must be absent. A file that BOTH gained and lost content needs both of the first two — the
added phrase passing says nothing about whether the removal survived. One does not
substitute for another, and each has a way to
lie: `grep` defaults to regex (use `-Fq --`), `git show ... | grep` returns 141 under
`pipefail` when grep exits early (capture to a file first), `grep -c` counts lines rather
than occurrences, and demanding *zero* occurrences rejects a correct partial removal.

```bash
(
  _chk=$(mktemp) || { echo "cannot create the scratch file — do NOT report the commit verified"; exit 1; }
  trap 'unlink "$_chk"' EXIT
  # ...the three loops, using `grep -Fq --` / `grep -Fo | wc -l || true` on a captured file.
)
```

The subshell keeps that temporary cleanup from replacing an `EXIT` trap owned by
the caller. A clean `git status` is neither check.

The same tools also corrupt without failing. In a `sed` replacement string `&`
means "the whole match", so substituting a value containing `&&` — any shell
command that chains, which is most of them — silently doubles it and reports
success. Substitute with something that treats the replacement as a literal, and
grep for the result afterwards.

**Never pipe a gate through `tail`, `head`, or `grep`.** A pipeline's exit status
is the last command's, and `tail` always succeeds, so a failing build reports
exit 0. Group the entire gate, use a fresh log, save the real status, and return
that status after reading the log:

```bash
POSIXLY_CORRECT=y
\unset -f command builtin exec unset
_gate_outer_bash=$(\command -p -v bash) ||
  { echo "cannot locate trusted Bash"; exit 1; }
\exec "$_gate_outer_bash" --noprofile --norc -p -s <<'__AGENT_GATE_WRAPPER__'
_gate_environment=$(command -p env) || exit 1
while IFS="=" read -r _gate_env_name _; do
  case $_gate_env_name in
    BASH_FUNC_command%%)
      printf "%s\n" "refusing exported command function" >&2
      exit 97
      ;;
    BASH_FUNC_*%%)
      printf "%s\n" "refusing exported shell function" >&2
      exit 97
      ;;
  esac
done <<<"$_gate_environment"
command type -P python3 >/dev/null 2>&1 ||
  { echo "python3 is required for gate supervision"; exit 1; }
_gate_dir=$(command mktemp -d) || { echo "cannot create gate directory"; exit 1; }
_gate_log="$_gate_dir/output.log"
_gate_error="$_gate_dir/error.log"
_gate_script="$_gate_dir/gate.bash"
_gate_runner="$_gate_dir/supervisor.py"
_gate_pending="$_gate_dir/exec.pending"
  _gate_remove_dir() {
    _gate_remove_rc=0
    for _gate_file in "$_gate_log" "$_gate_error" "$_gate_script" "$_gate_runner" "$_gate_pending"; do
      if [ -e "$_gate_file" ] && ! command unlink "$_gate_file"; then
        _gate_remove_rc=1
      fi
    done
    if ! command rmdir "$_gate_dir"; then
      _gate_remove_rc=1
    fi
    return "$_gate_remove_rc"
  }
  _gate_cleanup() {
    _gate_cleanup_rc=$?
    if ! _gate_remove_dir; then
      echo "cannot remove gate directory" >&2
      [ "$_gate_cleanup_rc" -ne 0 ] || _gate_cleanup_rc=1
    fi
    trap - EXIT
    exit "$_gate_cleanup_rc"
  }
  trap _gate_cleanup EXIT
  chmod 700 "$_gate_dir" || { echo "cannot protect gate directory"; exit 1; }
  if ! command cat >"$_gate_script" <<'__AGENT_GATE__'
<gate>
__AGENT_GATE__
  then
    echo "cannot write gate script"
    exit 1
  fi
  if ! command cat >"$_gate_runner" <<'__AGENT_SUPERVISOR__'
import os
import select
import signal
import subprocess
import sys
import time

root, bash, watchdog_pid, pending_path = sys.argv[1:5]
watchdog_pid = int(watchdog_pid)
log_path = os.path.join(root, "output.log")
error_path = os.path.join(root, "error.log")
gate_path = os.path.join(root, "gate.bash")
runner_path = os.path.join(root, "supervisor.py")
managed_signals = (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM)
child = None
gate_pgid = None
cancelled = None
signal_ready = False
pending_signal = None

class GateCancelled(BaseException):
    def __init__(self, signum):
        self.signum = signum


def receive_signal(signum, _frame):
    global pending_signal, signal_ready
    was_ready = signal_ready
    signal_ready = False
    if pending_signal is None:
        pending_signal = signum
    if not was_ready:
        return
    signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
    raise GateCancelled(pending_signal)


def ignore_managed_signals():
    for signum in managed_signals:
        signal.signal(signum, signal.SIG_IGN)


def write_terminal_status(stdout_fd, status):
    global signal_ready
    data = f"EXIT={status}\n".encode("ascii")
    while True:
        signal_ready = True
        _, writable, _ = select.select([], [stdout_fd], [], 0.1)
        if not writable:
            continue
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        signal_ready = False
        kernel_pending = signal.sigpending().intersection(managed_signals)
        if pending_signal is not None or kernel_pending:
            signum = pending_signal
            if signum is None:
                signum = min(kernel_pending)
            raise GateCancelled(signum)
        ignore_managed_signals()
        try:
            written = os.write(stdout_fd, data)
        except BaseException:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            raise
        if written != len(data):
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            raise RuntimeError("partial terminal status write")
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        return


def replay_worker(path, destination_fd):
    source_fd = None
    try:
        source_fd = os.open(path, os.O_RDONLY)
        while True:
            chunk = os.read(source_fd, 65536)
            if not chunk:
                os._exit(0)
            pending = memoryview(chunk)
            while pending:
                try:
                    written = os.write(destination_fd, pending)
                except BlockingIOError:
                    select.select([], [destination_fd], [], 0.1)
                    continue
                if written <= 0:
                    os._exit(1)
                pending = pending[written:]
    except BaseException:
        os._exit(1)
    finally:
        if source_fd is not None:
            os.close(source_fd)


def replay_logs(items):
    workers = []
    reaped = set()
    try:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        try:
            for path, destination_fd in items:
                pid = os.fork()
                if pid == 0:
                    try:
                        for signum in managed_signals:
                            signal.signal(signum, signal.SIG_DFL)
                        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                        replay_worker(path, destination_fd)
                    except BaseException:
                        os._exit(1)
                workers.append(pid)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        while len(reaped) != len(workers):
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
            try:
                for pid in workers:
                    if pid in reaped:
                        continue
                    waited, status = os.waitpid(pid, os.WNOHANG)
                    if waited == pid:
                        reaped.add(pid)
                        if (
                            not os.WIFEXITED(status)
                            or os.WEXITSTATUS(status) != 0
                        ):
                            raise RuntimeError("cannot replay gate output")
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            if len(reaped) != len(workers):
                time.sleep(0.05)
    except BaseException:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        try:
            for pid in workers:
                if pid not in reaped:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            for pid in workers:
                if pid not in reaped:
                    try:
                        os.waitpid(pid, 0)
                    except ChildProcessError:
                        pass
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        raise


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


subreaper_enabled = False


def enable_child_subreaper():
    global subreaper_enabled
    if not sys.platform.startswith("linux"):
        return
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = getattr(libc, "prctl", None)
    if prctl is None:
        raise OSError("Linux libc has no prctl")
    prctl.argtypes = (
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    )
    prctl.restype = ctypes.c_int
    if prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    subreaper_enabled = True


def reap_adopted_children():
    if not subreaper_enabled:
        return
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def stop_group(signum):
    global gate_pgid
    if child is None or gate_pgid is None:
        return True
    pgid = gate_pgid
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        pass
    try:
        os.killpg(pgid, signal.SIGCONT)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 0.2
    while group_alive(pgid) and time.monotonic() < deadline:
        time.sleep(0.01)
    if group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            return False
    deadline = time.monotonic() + 1.0
    while group_alive(pgid) and time.monotonic() < deadline:
        reap_adopted_children()
        time.sleep(0.01)
    reap_adopted_children()
    stopped = not group_alive(pgid)
    if stopped:
        gate_pgid = None
    return stopped


def remove_private_dir():
    ok = True
    for path in (log_path, error_path, gate_path, runner_path, pending_path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            ok = False
    try:
        os.rmdir(root)
    except FileNotFoundError:
        pass
    except OSError:
        ok = False
    return ok and not os.path.lexists(root)


for managed_signal in managed_signals:
    signal.signal(managed_signal, receive_signal)
signal.signal(signal.SIGCHLD, signal.SIG_DFL)
signal.pthread_sigmask(signal.SIG_UNBLOCK, managed_signals)

try:
    os.unlink(pending_path)
except FileNotFoundError:
    pass
try:
    os.kill(watchdog_pid, signal.SIGTERM)
except ProcessLookupError:
    pass
try:
    os.waitpid(watchdog_pid, 0)
except ChildProcessError:
    pass

rc = 1
try:
    signal_ready = True
    if pending_signal is not None:
        signal_ready = False
        signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        raise GateCancelled(pending_signal)
    enable_child_subreaper()
    environment = os.environ.copy()
    shell_control = {
        "BASHOPTS",
        "BASH_COMPAT",
        "BASH_ENV",
        "BASH_LOADABLES_PATH",
        "BASH_XTRACEFD",
        "CDPATH",
        "ENV",
        "GLOBIGNORE",
        "POSIXLY_CORRECT",
        "SHELLOPTS",
    }
    for name in tuple(environment):
        if name in shell_control or name.startswith("BASH_FUNC_"):
            environment.pop(name, None)
    environment["BASH_ENV"] = "/dev/null"
    with open(log_path, "wb") as output, open(error_path, "wb") as errors:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, managed_signals)
        try:
            child_bootstrap = (
                "import os,signal,sys;"
                "managed=tuple(map(int,sys.argv[3:]));"
                "signal.pthread_sigmask(signal.SIG_UNBLOCK,managed);"
                "os.execvpe(sys.argv[1],"
                "[sys.argv[1],'--noprofile','--norc','-eo','pipefail',sys.argv[2]],"
                "os.environ)"
            )
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    child_bootstrap,
                    bash,
                    gate_path,
                    *(str(signum) for signum in managed_signals),
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=errors,
                env=environment,
                start_new_session=True,
            )
            gate_pgid = child.pid
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        rc = child.wait()
        if rc < 0:
            rc = 128 - rc
        reap_adopted_children()
        if group_alive(gate_pgid):
            if not stop_group(signal.SIGTERM):
                print("cannot terminate gate process group", file=sys.stderr)
                rc = rc if rc != 0 else 1
            elif rc == 0:
                print("gate left background processes running", file=sys.stderr)
                rc = 1
        else:
            gate_pgid = None
except GateCancelled as cancellation:
    cancelled = cancellation.signum
    ignore_managed_signals()
    if not stop_group(cancellation.signum):
        print("cannot terminate gate process group", file=sys.stderr)
    rc = 128 + cancellation.signum
except BaseException as error:
    ignore_managed_signals()
    if gate_pgid is not None and group_alive(gate_pgid):
        stop_group(signal.SIGTERM)
    print(f"cannot run gate: {error}", file=sys.stderr)
    rc = rc if rc != 0 else 1
try:
    if cancelled is None:
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
        replay_logs(
            (
                (log_path, stdout_fd),
                (error_path, stderr_fd),
            )
        )
    if not remove_private_dir():
        print("cannot remove gate directory", file=sys.stderr)
        rc = rc if rc != 0 else 1
    if cancelled is None:
        write_terminal_status(stdout_fd, rc)
except GateCancelled as cancellation:
    cancelled = cancellation.signum
    ignore_managed_signals()
    if gate_pgid is not None and group_alive(gate_pgid):
        stop_group(cancellation.signum)
    rc = 128 + cancellation.signum
    if not remove_private_dir():
        print("cannot remove gate directory", file=sys.stderr)
except BaseException as error:
    ignore_managed_signals()
    print(f"cannot finalize gate: {error}", file=sys.stderr)
    rc = rc if rc != 0 else 1
    if not remove_private_dir():
        print("cannot remove gate directory", file=sys.stderr)
sys.exit(rc)
__AGENT_SUPERVISOR__
  then
    echo "cannot write gate supervisor"
    exit 1
  fi
: >"$_gate_pending" || { echo "cannot create exec marker"; exit 1; }
_gate_python=$(command type -P python3) ||
  { echo "cannot locate python3"; exit 1; }
command unset BASH_ENV ENV ||
  { echo "cannot clear shell startup environment"; exit 1; }
while command builtin read -r _ _ _gate_function; do
  command builtin export -n -f -- "$_gate_function" ||
    { echo "cannot clear exported shell function"; exit 1; }
done < <(command builtin declare -F)
_gate_owner_pid=$BASHPID
"$_gate_python" -I -c '
import os
import sys
import time

root, pending, owner_pid, *paths = sys.argv[1:]
owner_pid = int(owner_pid)
while os.path.lexists(pending):
    if os.getppid() != owner_pid:
        break
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        break
    except PermissionError:
        pass
    time.sleep(0.05)
if os.path.lexists(pending):
    for path in paths:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
    try:
        os.rmdir(root)
    except OSError:
        pass
' "$_gate_dir" "$_gate_pending" \
  "$_gate_owner_pid" "$_gate_log" "$_gate_error" "$_gate_script" "$_gate_runner" \
  "$_gate_pending" &
_gate_exec_watchdog=$!
command exec "$_gate_python" -I "$_gate_runner" "$_gate_dir" "${BASH:-bash}" \
  "$_gate_exec_watchdog" "$_gate_pending"
__AGENT_GATE_WRAPPER__
```

This portable supervisor requires Python 3 in addition to Bash; preflight it
before creating any private artifacts, as the snippet does. Run this as a
standalone final command, not as sourced setup for later commands:
`exec` makes the Python supervisor the caller-visible wrapper process, while a
failed `exec` leaves the shell cleanup trap armed. Put self-contained gate
commands between the delimiter lines. The supervisor runs them in a fresh Bash
from a private script with closed stdin, cleared shell-startup environment,
disabled startup files, and `pipefail`. The wrapper clears `BASH_ENV` and `ENV`
and removes the export attribute from every inherited shell function before
either Python launch as well, so a Python path implemented by a shell shim cannot
bypass the supervisor before its own environment sanitization runs. The entire
wrapper runs from a quoted here-document inside privileged Bash, so it cannot
import exported or non-exported caller functions. The caller first enables
POSIX special-builtin precedence, uses backslash-suppressed special builtins to
remove local functions named for the trust path, resolves Bash through
`command -p`, and replaces itself with that clean interpreter. Its
preflight refuses every raw exported-function environment entry before creating
artifacts, and the normal sanitizer is a second defense before either Python
launch.
It creates a dedicated process group and, after the supervisor has launched,
handles HUP, INT, QUIT, and TERM even when the invoking shell inherited an
ignored signal. Signals delivered earlier in the bootstrap can still retain
their inherited disposition. The supervisor resumes stopped work, waits with a
deadline, and escalates boundedly when the leader or another process in that
group ignores the signal. On Linux it also becomes a child subreaper before
launch, so orphaned descendants are reparented to and reaped by the supervisor
rather than leaving a zombie-only group that POSIX `kill(0)` cannot distinguish
from live work; failure to establish that Linux contract is fail-closed. Other
platforms keep the portable process-group contract. Gate commands must use their
foreground mode and must not daemonize into a different session/process group;
that is outside this portable wrapper's containment contract. Cleanup happens
before the reported final status: supervisor, read,
lingering-process, or cleanup failure turns success into failure but preserves
an existing nonzero/signal status. The wrapper returns that final status,
including categorized statuses such as 2 or 124.

**"Passing", "clean", "working", "verified", and "done" require a command and an
exit code.** If you cannot show one, say what you actually observed instead. This
is the single most common way an agent reports success it did not have.

**A claim about what a tool does needs a run, not a recollection.** Prose asserting
observable behaviour — an exit code, which stream output went to, which versions were
tested — is as capable of being wrong as code, and nothing compiles it. Record enough that
a reader can re-run it and disagree: the command, the versions, the mode where the mode
changes the answer, and the observed result with the streams *separated by redirection*
rather than labelled by hand. Two things that are not records: a bare "Measured on
git 2.54.0", which names no command or result, and "fails silently", which names no
version or mode. And observing is not explaining — a rerun gives you the exit code and the
streams, never the *why*; "X fails because Y" needs Y varied on its own with the outcome
changing, or the documentation cited. Absent that, write what you saw and leave the cause
out. A claim you cannot run — a version you do not have — is not yours to assert: say it
is unmeasured and narrow it to a possibility.

**Reviewers read code; they do not run it.** A clean review — human, bot, or
model — is not a passing build. Run the gate yourself before calling anything
done.

**A test that has never failed has proven nothing.** When you add one for a bug,
watch it go red against the unfixed code first. A test asserting behaviour that
was already correct is indistinguishable from a test asserting nothing.

Three things decide whether that red run means anything. Break the **production
behaviour**, never the test's expected value or its setup — those redden any
assertion, including one that never reaches the behaviour. **Read the failure**: it
must name the assertion pinning what you broke, not an unrelated panic. And run **one
mutation per property** the test claims, since reddening the first of two leaves the
second untested while looking verified. If the test drives anything live — a real
database, a running service, real money — do the red run in a disposable environment
or not at all: a deliberately broken build can perform the harmful operation before
any assertion notices.

Gate for this repo: `bash tools/check-all.sh`
<!-- end-agent-discipline -->

<!-- br-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`/`bd`) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View ready issues (open, unblocked, not deferred)
br ready              # or: bd ready

# List and search
br list --status=open # All open issues
br show <id>          # Full issue details with dependencies
br search "keyword"   # Full-text search

# Create and update
br create --title="..." --description="..." --type=task --priority=2
br update <id> --status=in_progress
br close <id> --reason="Completed"
br close <id1> <id2>  # Close multiple issues at once

# Sync with git
br sync --flush-only  # Export DB to JSONL
br sync --status      # Check sync status
```

### Workflow Pattern

1. **Start**: Run `br ready` to find actionable work
2. **Claim**: Use `br update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `br close <id>`
5. **Sync**: Always run `br sync --flush-only` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only open, unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
br sync --flush-only    # Export beads changes to JSONL
git commit -m "..."     # Commit everything
git push                # Push to remote
```

### Best Practices

- Check `br ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always sync before ending session

<!-- end-br-agent-instructions -->
