# filters output
import shlex
import subprocess


class CommandExecutionManager:
    @staticmethod
    def run(command, stream_output=True):
        """Run a command with arguments and stream the output to the console if enabled"""
        try:
            _proc_stdout = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
            while True:
                output = _proc_stdout.stdout.readline()
                if _proc_stdout.poll() is not None:
                    break
                if stream_output and output:
                    print(output.strip().decode(encoding="utf-8"))
            return _proc_stdout.poll()
        except FileNotFoundError:
            return f"[ERR] Error while trying to run command '{command}'"
        except Exception as e:
            return e
