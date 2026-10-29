"""An explicitly configured local alignment adapter; commands never come from documents."""

import json
import os
import subprocess
import tempfile
import time

from ...errors import VixlError, require
from ...calls import check_cancelled
from ...model import finite

MAX_OUTPUT = 4 * 1024 * 1024


class CommandProvider:
    def __init__(self, name, config):
        self.name, self.config = name, config
        command = config.get("command")
        require(isinstance(command, list) and 1 <= len(command) <= 32 and
                all(isinstance(arg, str) and arg and "\0" not in arg for arg in command),
                "Alignment command must be an argv array in providers.json; see docs/reference/providers.md",
                "provider_not_configured")

    def invoke(self, capability, request):
        check_cancelled()
        require(capability == "align", "Command providers support only align", "unsupported_capability")
        timeout = finite(self.config.get("timeout", 120), "provider timeout", 1, 600)
        # Temporary streams bound memory and let us stop a noisy child before reading its output.
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            source.write(json.dumps(request, ensure_ascii=False).encode())
            source.seek(0)
            try:
                process = subprocess.Popen(self.config["command"], stdin=source, stdout=output, stderr=errors,
                                           shell=False)
            except OSError as exc:
                raise VixlError("missing_dependency", "Alignment command could not start; check providers.json") from exc
            try:
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    check_cancelled()
                    require(time.monotonic() < deadline, "Alignment command timed out", "provider_timeout")
                    require(max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) <= MAX_OUTPUT,
                            "Alignment command output exceeds 4 MiB", "resource_limit")
                    time.sleep(0.02)
                require(max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) <= MAX_OUTPUT,
                        "Alignment command output exceeds 4 MiB", "resource_limit")
                check_cancelled()
                require(process.returncode == 0, "Alignment command failed; inspect the adapter locally", "provider_error")
                output.seek(0)
                data = output.read(MAX_OUTPUT + 1)
                require(len(data) <= MAX_OUTPUT, "Alignment command output exceeds 4 MiB", "resource_limit")
                try:
                    value = json.loads(data)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise VixlError("provider_error", "Alignment command must return JSON on stdout") from exc
                require(isinstance(value, dict), "Alignment command must return a JSON object", "provider_error")
                return value
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
