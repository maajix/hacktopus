import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml


class ToolEnums(Enum):
    """
    Enum to handle the different tool types
    """
    TOOLS_DIR_NAME = "tools"
    ALIAS_FILE = "aliases.yaml"


@dataclass
class ToolFileHandler:
    """
    Dataclass to handle the tool file paths
    """
    tool_name: str = None
    alias_content: dict = None
    root_dir: str = Path(__file__).parent.parent.parent.absolute()
    tool_dir: str = Path(root_dir, ToolEnums.TOOLS_DIR_NAME.value)


@dataclass
class FlowHandler:
    """
    Dataclass to handle the flow file paths
    """
    stage_info: dict = None
    stage_options: dict = None
    alias_command: str = None


class CLIBuilder:
    """
    Class to convert a list of stage aliases to usable CLI commands
    """
    def __init__(self):
        self.tool_file_handler = ToolFileHandler()
        self.flowHandler = FlowHandler()

    def alias_to_command(self, alias: str) -> str:
        """
        Convert a given alias to a CLI command
        :param alias: Alias to convert

        :Example:
        >>> CLIBuilder.alias_to_command("paramspider:default")
        paramspider -s -d {{url}}
        """

        try:
            """Split the given tool shortcut into tool and alias"""
            tool, alias = alias.split(":")
        except Exception as e:
            print(f"[ERR] Could not find ':' delimiter in alias: {alias}")
            return str(e)

        aliases_file = Path(self.tool_file_handler.tool_dir, tool, ToolEnums.ALIAS_FILE.value)

        if os.path.exists(aliases_file):
            with open(aliases_file, 'r') as f:
                try:
                    self.tool_file_handler.alias_content = yaml.safe_load(f)
                except Exception as e:
                    print(f"[ERR] Could not load aliases file: {aliases_file}")
                    return str(e)
        else:
            print(f"[ERR] Aliases file not found: {aliases_file}")

        for _alias in self.tool_file_handler.alias_content["aliases"]:
            if _alias == alias:
                try:
                    self.flowHandler.alias_command = (
                            tool + " " + self.tool_file_handler.alias_content
                            .get("aliases")
                            .get(_alias)
                            .get("command")
                    )
                    break
                except Exception as e:
                    print(f"[ERR] Could not parse command for alias: {alias}")
                    return str(e)
            else:
                print(f"[ERR] Alias '{alias}' not found for tool '{tool}'")

        return self.flowHandler.alias_command
