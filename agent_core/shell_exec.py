import subprocess

def run_shell_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60  # prevent hangups
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out."
    except Exception as e:
        return f"[ERROR] Execution failed: {str(e)}"
