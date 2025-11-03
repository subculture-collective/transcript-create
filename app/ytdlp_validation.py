"""
yt-dlp JavaScript runtime validation.

This module provides validation for JavaScript runtime requirements needed by yt-dlp
to solve YouTube challenges and extract video information.
"""

import shutil
import subprocess
from typing import Optional, Tuple

from prometheus_client import Counter

from .logging_config import get_logger
from .settings import settings

logger = get_logger(__name__)

# Metrics for JS runtime validation
ytdlp_js_runtime_check_total = Counter(
    "ytdlp_js_runtime_check_total",
    "Total JS runtime validation checks performed",
    ["result"],
)


def check_js_runtime_available() -> Tuple[bool, Optional[str]]:
    """
    Check if the configured JavaScript runtime is available.

    Returns:
        Tuple[bool, Optional[str]]: (is_available, error_message)
            - is_available: True if JS runtime is found, False otherwise
            - error_message: None if available, detailed error message otherwise
    """
    js_runtime = settings.JS_RUNTIME_CMD.strip()

    if not js_runtime:
        error_msg = (
            "JS_RUNTIME_CMD is not configured. "
            "yt-dlp requires a JavaScript runtime to solve YouTube challenges."
        )
        return False, error_msg

    # Check if runtime command exists
    runtime_path = shutil.which(js_runtime)
    if not runtime_path:
        error_msg = (
            f"JavaScript runtime '{js_runtime}' not found in PATH. "
            f"yt-dlp requires a JS runtime (Deno/Node/Bun/QuickJS) to solve YouTube challenges."
        )
        return False, error_msg

    logger.debug(f"Found JS runtime: {js_runtime} at {runtime_path}")
    return True, None


def validate_ytdlp_with_js_runtime() -> Tuple[bool, Optional[str]]:
    """
    Validate that yt-dlp can run with the configured JavaScript runtime.

    This performs a quick smoke test by running yt-dlp --version to ensure
    the runtime integration works.

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
            - is_valid: True if yt-dlp works with JS runtime, False otherwise
            - error_message: None if valid, detailed error message otherwise
    """
    # First check if JS runtime is available
    runtime_available, runtime_error = check_js_runtime_available()
    if not runtime_available:
        return False, runtime_error

    # Check if yt-dlp is available
    ytdlp_path = shutil.which("yt-dlp")
    if not ytdlp_path:
        error_msg = "yt-dlp not found in PATH. Please install yt-dlp."
        return False, error_msg

    # Run yt-dlp --version as a smoke test
    # This is lightweight and validates that the basic setup works
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        logger.debug(f"yt-dlp version check succeeded: {result.stdout.strip()}")
        return True, None
    except subprocess.TimeoutExpired:
        error_msg = (
            "yt-dlp --version timed out. "
            "This may indicate a problem with the JS runtime configuration."
        )
        return False, error_msg
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"yt-dlp --version failed with return code {e.returncode}. "
            f"Error: {e.stderr.strip() if e.stderr else 'Unknown error'}"
        )
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error running yt-dlp: {str(e)}"
        return False, error_msg


def get_installation_instructions() -> str:
    """
    Get installation instructions for JavaScript runtime.

    Returns:
        str: Formatted installation instructions with remediation steps
    """
    js_runtime = settings.JS_RUNTIME_CMD.strip()

    # Use custom hint if provided
    if settings.YTDLP_JS_RUNTIME_HINT:
        return settings.YTDLP_JS_RUNTIME_HINT

    # Default installation instructions
    instructions = {
        "deno": """
Install Deno (recommended):
  - Linux/macOS: curl -fsSL https://deno.land/install.sh | sh
  - Windows: irm https://deno.land/install.ps1 | iex
  - Homebrew: brew install deno
  - More: https://docs.deno.com/runtime/getting_started/installation/

After installation, ensure 'deno' is in your PATH.
""",
        "node": """
Install Node.js:
  - Linux: Use your package manager (e.g., apt install nodejs)
  - macOS: brew install node
  - Windows: Download from https://nodejs.org/
  - More: https://nodejs.org/en/download/package-manager

After installation, ensure 'node' is in your PATH.
""",
        "bun": """
Install Bun:
  - Linux/macOS: curl -fsSL https://bun.sh/install | bash
  - Windows: powershell -c "irm bun.sh/install.ps1|iex"
  - More: https://bun.sh/docs/installation

After installation, ensure 'bun' is in your PATH.
""",
        "quickjs": """
Install QuickJS:
  - Linux: Use your package manager (e.g., apt install quickjs)
  - macOS: brew install quickjs
  - Compile from source: https://bellard.org/quickjs/

After installation, ensure 'quickjs' is in your PATH.
""",
    }

    return instructions.get(
        js_runtime,
        f"""
Install a JavaScript runtime:
  - Deno (recommended): https://docs.deno.com/runtime/getting_started/installation/
  - Node.js: https://nodejs.org/
  - Bun: https://bun.sh/
  - QuickJS: https://bellard.org/quickjs/

After installation, configure JS_RUNTIME_CMD in .env to point to your runtime.
Current configuration: JS_RUNTIME_CMD={js_runtime}
""",
    )


def validate_js_runtime_or_exit() -> None:
    """
    Validate JavaScript runtime availability and exit if validation fails.

    This function should be called at startup to ensure yt-dlp can function properly.
    If validation fails, it logs a clear error message with remediation steps and exits.
    """
    # Skip validation if disabled
    if not settings.YTDLP_REQUIRE_JS_RUNTIME:
        logger.info("JS runtime validation is disabled (YTDLP_REQUIRE_JS_RUNTIME=false)")
        ytdlp_js_runtime_check_total.labels(result="skipped").inc()
        return

    logger.info("Validating JavaScript runtime for yt-dlp...")

    # Perform validation
    is_valid, error_msg = validate_ytdlp_with_js_runtime()

    if is_valid:
        logger.info(
            "JavaScript runtime validation successful",
            extra={
                "runtime": settings.JS_RUNTIME_CMD,
                "runtime_args": settings.JS_RUNTIME_ARGS,
            },
        )
        ytdlp_js_runtime_check_total.labels(result="success").inc()
        return

    # Validation failed - log error and exit
    logger.error(
        "JavaScript runtime validation failed",
        extra={
            "runtime": settings.JS_RUNTIME_CMD,
            "error": error_msg,
        },
    )
    ytdlp_js_runtime_check_total.labels(result="failure").inc()

    # Print clear error message to stderr
    error_output = f"""
╔════════════════════════════════════════════════════════════════════════════╗
║                   JAVASCRIPT RUNTIME NOT AVAILABLE                         ║
╚════════════════════════════════════════════════════════════════════════════╝

ERROR: {error_msg}

yt-dlp now requires a JavaScript runtime (Deno/Node/Bun/QuickJS) to solve
YouTube challenges and extract video information.

{get_installation_instructions()}

To disable this check (not recommended), set:
  YTDLP_REQUIRE_JS_RUNTIME=false

For more information, see:
  - yt-dlp JS runtime: https://github.com/yt-dlp/yt-dlp#dependencies
  - Project documentation: README.md

"""
    print(error_output, flush=True)

    # Exit with non-zero status
    import sys

    sys.exit(1)
