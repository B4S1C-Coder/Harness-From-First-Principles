from typing import Any
from ..tools import BaseTool, ToolRegistry
from ..sandboxes import VirtualFileSystemSandbox
from ..limits import VirtualFSReadLimits
from ..exceptions import ValueValidationError

class VirtualFSTool(BaseTool):
    """ Shared dependency for virtual file system tools. """

    def __init__(
            self,
            sandbox: VirtualFileSystemSandbox,
            *,
            limit: VirtualFSReadLimits | None = None,
        ) -> None:
        self.sandbox = sandbox
        self.limit = limit or VirtualFSReadLimits()

@ToolRegistry.register
class ListDirectoryTool(VirtualFSTool):
    name = "list_directory"
    description = "List files and directories in the workspace."

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative directory path.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]

        return {
            "path": path,
            "listing": self.sandbox.list_directory(path),
        }

@ToolRegistry.register
class ReadFileTool(VirtualFSTool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file from the workspace. "
        "Large files are truncated. Use read_lines to inspect specific sections."
    )

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative file path.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]

        return {
            "path": path,
            "content": self.sandbox.read_file(path, max_bytes=self.limit.max_bytes)
        }

@ToolRegistry.register
class ReadLinesTool(VirtualFSTool):
    name = "read_lines"
    description = (
        "Read a specific inclusive range of lines from a workspace file. "
        "Line numbers start at 1. The tool will inform in case of truncated output."
    )

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative file path.",
            },
            "start_line": {
                "type": "integer",
                "minimum": 1,
                "description": "First line to read (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "minimum": 1,
                "description": "Last line to readm(inclusive).",
            },
        },
        "required": ["path", "start_line", "end_line"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        path, start_line, req_end_line = args["path"], args["start_line"], args["end_line"]

        if req_end_line < start_line:
            raise ValueValidationError("end_line must be >= start_line.")

        end_line = min(
            req_end_line, start_line + self.limit.max_lines - 1
        )

        return {
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "truncated_range": end_line < req_end_line,
            "content": self.sandbox.read_lines(
                path,
                start_line=start_line,
                end_line=end_line,
                max_bytes=self.limit.max_bytes,
                max_lines=self.limit.max_lines,
            ),
        }

@ToolRegistry.register
class WriteFileTool(VirtualFSTool):
    name = "write_file"
    description = (
        "Create a UTF-8 text file in the workspace. "
        "Set overwrite=true to completely replace an existing file. "
        "Parent directories must already exist."
    )

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative file path.",
            },
            "content": {
                "type": "string",
                "description": "Complete content to write.",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Whether to replace an existing file.",
                "default": False,
            },
        },
        "required": ["path", "content", "overwrite"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]

        self.sandbox.write_file(
            path,
            args["content"],
            overwrite=args.get("overwrite", False),
        )

        return {
            "path": path,
            "written": True,
        }


@ToolRegistry.register
class EditFileTool(VirtualFSTool):
    name = "edit_file"
    description = (
        "Replace an inclusive range of lines in a workspace text file. "
        "Line numbers start at 1. Replaces all lines in the range "
        "with the supplied content. Empty content deletes the range. "
        "Read the relevant lines before editing."
    )

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative file path.",
            },
            "start_line": {
                "type": "integer",
                "minimum": 1,
                "description": "First line to replace (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "minimum": 1,
                "description": "Last line to replace (inclusive).",
            },
            "content": {
                "type": "string",
                "description": (
                    "Replacement text. Use an empty string to delete the lines."
                ),
            },
        },
        "required": ["path", "start_line", "end_line", "content"],
        "additionalProperties": False,
    }

    def driver(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]

        self.sandbox.edit_file(
            path,
            start_line=args["start_line"],
            end_line=args["end_line"],
            content=args["content"],
        )

        return {
            "path": path,
            "edited": True,
            "start_line": args["start_line"],
            "end_line": args["end_line"],
        }
