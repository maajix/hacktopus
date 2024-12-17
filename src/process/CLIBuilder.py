import os
from pathlib import Path

import yaml

from .Flow import Flow


class CLIBuilder:
    """
    Class to convert a list of stage aliases to usable CLI commands
    """
    flow = Flow()
    _stage_information = flow.get_stage_information()
    _stage_options = flow.get_state_options()
    _ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
    _TOOL_PATH = Path(_ROOT_DIR, "tools")

    _ALIASES_FILE_CONTENT = None
    _UNFILTERED_ALIAS_COMMAND = None

    def __init__(self, Flow: Flow):
        self.flow = Flow

    def alias_to_command(self, alias) -> str:
        """
        :param alias: Syntax <tool>:<alias>
        :return: Unfiltered (containing variables) CLI command for the given alias
        """

        try:
            """Split the given tool shortcut into tool and alias"""
            tool, alias = alias.split(":")
        except Exception as e:
            print(f"[ERR] Could not find ':' delimiter in alias: {alias}")
            return e

        aliases_file = Path(self._TOOL_PATH, tool, "aliases.yaml")

        if os.path.exists(aliases_file):
            with open(aliases_file, 'r') as f:
                try:
                    data = yaml.safe_load(f)
                    self._ALIASES_FILE_CONTENT = data if data is not None else {}
                except Exception as e:
                    print(f"[ERR] Could not load aliases file: {aliases_file}")
                    return e
        else:
            print(f"[ERR] Aliases file not found: {aliases_file}")

        for _alias in self._ALIASES_FILE_CONTENT["aliases"]:
            if _alias == alias:
                try:
                    self._UNFILTERED_ALIAS_COMMAND = (
                            tool + " " + self._ALIASES_FILE_CONTENT
                            .get("aliases")
                            .get(_alias)
                            .get("command")
                    )
                    break
                except Exception as e:
                    print(f"[ERR] Could not parse command for alias: {alias}")
                    return e
            else:
                print(f"[ERR] Alias '{alias}' not found for tool '{tool}'")

        return self._UNFILTERED_ALIAS_COMMAND
