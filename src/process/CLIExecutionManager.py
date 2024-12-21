# filters output
import shlex
import subprocess
from typing import Protocol


class Flow(Protocol):
    @property
    def execution_dict(self):
        ...


class CommandExecutionManager:
    """
    A class to manage the execution of command line commands
    """

    @staticmethod
    def run(command: str, stream_live_output: bool = True):
        """
        Run a command with arguments and stream the output to the console if enabled

        :param command: The command to run
        :param stream_live_output: Stream the live output to the console
        :return: The return code of the command

        :Example:
        >>> CommandExecutionManager.run("echo 'Hello World'")
        Hello World
        """
        try:
            _proc_stdout = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
            while True:
                output = _proc_stdout.stdout.readline()
                if _proc_stdout.poll() is not None:
                    break
                if stream_live_output and output:
                    print(output.strip().decode(encoding="utf-8"))
            return _proc_stdout.poll()
        except FileNotFoundError:
            return f"[ERR] Error while trying to run command '{command}'"  # @TODO: Check if return works with threading
        except Exception as e:
            return e

    @staticmethod
    def run_flow(flow: Flow):
        """
        Run a flow @TODO

        :param flow: The flow to run
        :return: The return code of the command

        :Example:
        >>> CommandExecutionManager.run_flow(Flow)
        """
        print(f"Running flow '{flow.execution_dict}'")
        pass
