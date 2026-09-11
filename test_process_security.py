import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import monitor


class ProcessSecurityTests(unittest.TestCase):
    def run_python(self, code, timeout=1, **limits):
        path = os.path.realpath(sys.executable)
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        try:
            return monitor.bounded_process(path, fd, ['-I', '-c', code], timeout, **limits)
        finally:
            os.close(fd)

    def test_normal_output_and_environment(self):
        with patch.dict(os.environ, {'PATH': '/untrusted', 'PYTHONPATH': '/bad', 'LD_LIBRARY_PATH': '/bad', 'QUIKVIEW_SECRET': 'hidden'}):
            output = self.run_python("import os,json; print(json.dumps(dict(os.environ)))")
        import json
        self.assertEqual(json.loads(output), monitor.TOOL_ENV)

    def test_stdout_limit(self):
        with self.assertRaisesRegex(monitor.ToolUnavailable, 'stdout limit'):
            self.run_python("import os; os.write(1,b'x'*8192)", stdout_limit=1024)

    def test_stderr_limit(self):
        with self.assertRaisesRegex(monitor.ToolUnavailable, 'stderr limit'):
            self.run_python("import os; os.write(2,b'x'*8192)", stderr_limit=1024)

    def test_exact_limit_is_allowed(self):
        self.assertEqual(self.run_python("import os; os.write(1,b'x'*1024)", stdout_limit=1024), 'x' * 1024)

    def test_nonzero_exit(self):
        with self.assertRaisesRegex(monitor.ToolUnavailable, 'unsuccessfully'):
            self.run_python("raise SystemExit(3)")

    def test_timeout_with_closed_pipes_and_ignored_sigterm(self):
        start = time.monotonic()
        with self.assertRaisesRegex(monitor.ToolUnavailable, 'deadline'):
            self.run_python("import os,time,signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); os.close(1); os.close(2); time.sleep(30)", timeout=.2)
        self.assertLess(time.monotonic() - start, 2)

    def assert_child_stopped(self, code, fail=False):
        with tempfile.TemporaryDirectory() as temp:
            pidfile = Path(temp) / 'child.pid'
            code = code.replace('PIDFILE', repr(str(pidfile)))
            if fail:
                with self.assertRaises(monitor.ToolUnavailable):
                    self.run_python(code, timeout=.4, stdout_limit=1024)
            else:
                self.run_python(code)
            pid = int(pidfile.read_text())
            # An orphan zombie is stopped but may await the system's reaper.
            for _ in range(50):
                try:
                    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                    if fields[0] == 'Z':
                        return
                except FileNotFoundError:
                    return
                time.sleep(.01)
            self.fail('Descendant still running after cleanup')

    def test_timeout_kills_descendant_holding_pipes(self):
        self.assert_child_stopped("""
import os,time
pid=os.fork()
if pid == 0:
    time.sleep(30)
else:
    open(PIDFILE,'w').write(str(pid))
    os._exit(0)
""", fail=True)

    def test_success_still_kills_descendant(self):
        self.assert_child_stopped("""
import os,time
pid=os.fork()
if pid == 0:
    os.close(1); os.close(2); time.sleep(30)
else:
    open(PIDFILE,'w').write(str(pid))
    time.sleep(.05)
""")

    def test_output_limit_kills_descendant(self):
        self.assert_child_stopped("""
import os,time
pid=os.fork()
if pid == 0:
    time.sleep(30)
else:
    open(PIDFILE,'w').write(str(pid))
    os.write(1,b'x'*8192)
    time.sleep(30)
""", fail=True)

    def test_executes_verified_inode_after_path_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tool'
            shutil.copy2(os.path.realpath(sys.executable), path)
            fd = os.open(path, os.O_RDONLY)
            try:
                path.unlink()
                path.symlink_to('/usr/bin/false')
                self.assertEqual(monitor.bounded_process(str(path), fd, ['-I', '-c', 'print("verified")'], 1), 'verified\n')
            finally:
                os.close(fd)

    def test_unknown_or_missing_tool_falls_back(self):
        self.assertIsNone(monitor.tool_output('not-allowed', [], 1))
        with patch.dict(monitor.TOOLS, {'lspci': '/usr/bin/quikview-nonexistent-tool'}):
            self.assertIsNone(monitor.tool_output('lspci', [], 1))

    def test_path_candidate_is_never_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'executed'
            candidate = Path(temp) / 'lspci'
            candidate.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n')
            candidate.chmod(0o755)
            with patch.dict(os.environ, {'PATH': temp}):
                monitor.tool_output('lspci', ['--version'], 1)
            self.assertFalse(marker.exists())

    def test_untrusted_owner_and_modes(self):
        info = list(os.stat(os.path.realpath(sys.executable)))
        for uid, mode in [(1000, stat.S_IFREG | 0o755), (0, stat.S_IFREG | 0o777), (0, stat.S_IFREG | 0o4755), (0, stat.S_IFIFO | 0o600)]:
            altered = info.copy()
            altered[4] = uid
            altered[0] = mode
            with self.subTest(uid=uid, mode=mode), self.assertRaises(monitor.ToolUnavailable):
                monitor.trusted_node(os.stat_result(altered))

    def test_symlinks_and_non_elf_refused(self):
        # Model a root-owned fixture without requiring privileged chown.
        actual_fstat = os.fstat
        def root_owned(fd):
            fields = list(actual_fstat(fd))
            fields[4] = 0
            fields[0] &= ~0o022
            return os.stat_result(fields)
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'binary'
            shutil.copy2(os.path.realpath(sys.executable), binary)
            alias = Path(temp) / 'alias'
            alias.symlink_to(binary)
            script = Path(temp) / 'script'
            script.write_text('#!/bin/sh\necho bad\n')
            script.chmod(0o755)
            folder = Path(temp) / 'folder'
            folder.symlink_to(temp, target_is_directory=True)
            for candidate in (alias, script, folder / 'binary'):
                with self.subTest(path=candidate), patch.object(monitor.os, 'fstat', side_effect=root_owned), patch.dict(monitor.TOOLS, {'lspci': str(candidate)}):
                    with self.assertRaises((OSError, monitor.ToolUnavailable)):
                        with monitor.verified_tool('lspci'):
                            self.fail('Unsafe executable accepted')


if __name__ == '__main__':
    unittest.main()
