"""
Tier 3: Vault Tools - The Crafting Hands

File operations mapped to the existing Vault API.
User-scoped, quota-enforced file management.
"Shape and mold the user's files"

NOTE: These tools require database access with user context.
They use SQLAlchemy models directly rather than HTTP endpoints.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)


async def get_db_session():
    """Get a database session for tool operations."""
    from app.database import async_session
    async with async_session() as session:
        yield session


# =============================================================================
# VAULT LIST
# =============================================================================

class VaultListTool(BaseTool):
    """List files and folders in the user's vault."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vault_list",
            description="""List files and folders in the user's vault.

Use to:
- Browse the user's file storage
- Find specific files by name
- Navigate folder hierarchy

Returns file names, sizes, and types. Root folder is used if no folder_id specified.""",
            category=ToolCategory.FILES,
            input_schema={
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "string",
                        "description": "Folder UUID to list (omit for root folder)",
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required to access vault")

        folder_id = params.get("folder_id")

        try:
            from app.models.file import File, Folder
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Get folder (root if not specified)
                if folder_id:
                    folder_uuid = UUID(folder_id)
                    folder_result = await db.execute(
                        select(Folder).where(
                            Folder.id == folder_uuid,
                            Folder.user_id == user_uuid
                        )
                    )
                    folder = folder_result.scalar_one_or_none()
                    if not folder:
                        return ToolResult(success=False, error=f"Folder not found: {folder_id}")
                else:
                    # Get root folder
                    folder_result = await db.execute(
                        select(Folder).where(
                            Folder.user_id == user_uuid,
                            Folder.parent_id == None  # noqa: E711
                        )
                    )
                    folder = folder_result.scalar_one_or_none()
                    if not folder:
                        return ToolResult(
                            success=True,
                            result={"folder_id": "root", "folders": [], "files": [], "total_items": 0}
                        )

                # Get subfolders
                subfolders_result = await db.execute(
                    select(Folder).where(
                        Folder.parent_id == folder.id,
                        Folder.user_id == user_uuid
                    )
                )
                subfolders = subfolders_result.scalars().all()

                # Get files in folder
                files_result = await db.execute(
                    select(File).where(
                        File.folder_id == folder.id,
                        File.user_id == user_uuid
                    )
                )
                files = files_result.scalars().all()

                folders_list = [
                    {"id": str(f.id), "name": f.name}
                    for f in subfolders
                ]

                files_list = [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "size": f.size_bytes,
                        "mime_type": f.mime_type,
                    }
                    for f in files
                ]

                return ToolResult(
                    success=True,
                    result={
                        "folder_id": str(folder.id),
                        "folder_name": folder.name,
                        "folders": folders_list,
                        "files": files_list,
                        "total_items": len(folders_list) + len(files_list),
                    },
                )

        except Exception as e:
            logger.exception("Vault list error")
            return ToolResult(success=False, error=f"Failed to list vault: {str(e)}")


# =============================================================================
# VAULT READ
# =============================================================================

class VaultReadTool(BaseTool):
    """Read content from a file in the vault."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vault_read",
            description="""Read the content of a text file from the user's vault.

Use to:
- Read code files (Python, JavaScript, etc.)
- Read markdown or text documents
- Get configuration files

Note: Only text files are supported. Binary files will return metadata only.""",
            category=ToolCategory.FILES,
            input_schema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "File UUID to read",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Max content length to return (default: 50000)",
                        "default": 50000,
                    },
                },
                "required": ["file_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required to access vault")

        file_id = params.get("file_id")
        max_length = min(params.get("max_length", 50000), 100000)

        if not file_id:
            return ToolResult(success=False, error="file_id is required")

        try:
            from app.models.file import File
            from app.database import async_session
            from pathlib import Path

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                file_uuid = UUID(file_id)

                # Get file record
                file_result = await db.execute(
                    select(File).where(
                        File.id == file_uuid,
                        File.user_id == user_uuid
                    )
                )
                file = file_result.scalar_one_or_none()

                if not file:
                    return ToolResult(success=False, error=f"File not found: {file_id}")

                # Check if text file
                is_text = file.mime_type and (
                    file.mime_type.startswith("text/") or
                    file.mime_type in [
                        "application/json",
                        "application/javascript",
                        "application/xml",
                        "application/x-python",
                    ] or
                    file.name.endswith(('.py', '.js', '.ts', '.md', '.txt', '.json', '.yaml', '.yml', '.html', '.css'))
                )

                result = {
                    "id": str(file.id),
                    "name": file.name,
                    "size": file.size_bytes,
                    "mime_type": file.mime_type,
                    "is_text": is_text,
                }

                if is_text and file.storage_path:
                    # Read from filesystem - storage_path is the full path
                    file_path = Path(file.storage_path)

                    if file_path.exists():
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        if len(content) > max_length:
                            content = content[:max_length] + "\n\n[Truncated...]"
                            result["truncated"] = True
                        result["content"] = content
                    else:
                        result["error"] = "File content not found on disk"

                return ToolResult(success=True, result=result)

        except Exception as e:
            logger.exception("Vault read error")
            return ToolResult(success=False, error=f"Failed to read file: {str(e)}")


# =============================================================================
# VAULT INFO
# =============================================================================

class VaultInfoTool(BaseTool):
    """Get storage usage and quota information."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vault_info",
            description="""Get the user's vault storage statistics.

Returns:
- Total storage used
- Storage quota/limit
- File count
- Folder count

Use to check available space before creating files.""",
            category=ToolCategory.FILES,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required to access vault")

        try:
            from app.models.file import File, Folder
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Count files and total size
                files_result = await db.execute(
                    select(
                        func.count(File.id).label("count"),
                        func.coalesce(func.sum(File.size_bytes), 0).label("total_size")
                    ).where(File.user_id == user_uuid)
                )
                file_stats = files_result.one()

                # Count folders
                folders_result = await db.execute(
                    select(func.count(Folder.id)).where(Folder.user_id == user_uuid)
                )
                folder_count = folders_result.scalar() or 0

                used_bytes = file_stats.total_size or 0
                quota_bytes = 100 * 1024 * 1024  # 100MB default

                return ToolResult(
                    success=True,
                    result={
                        "used_bytes": used_bytes,
                        "used_human": _format_size(used_bytes),
                        "quota_bytes": quota_bytes,
                        "quota_human": _format_size(quota_bytes),
                        "percent_used": round(used_bytes / quota_bytes * 100, 1),
                        "file_count": file_stats.count or 0,
                        "folder_count": folder_count,
                    },
                )

        except Exception as e:
            logger.exception("Vault info error")
            return ToolResult(success=False, error=f"Failed to get vault info: {str(e)}")


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# =============================================================================
# VAULT WRITE
# =============================================================================

class VaultWriteTool(BaseTool):
    """Write content to a file in the vault."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vault_write",
            description="""Write content to a file in the user's vault.

Use to:
- Create new text files (code, notes, configs)
- Update existing file content
- Save generated content for the user

Supports text files only (code, documents, data).
Respects user's storage quota.""",
            category=ToolCategory.FILES,
            input_schema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "File UUID to update (omit to create new file)",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename for new file (required if no file_id)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write",
                    },
                    "folder_id": {
                        "type": "string",
                        "description": "Folder UUID for new file (omit for root)",
                    },
                },
                "required": ["content"],
            },
            requires_auth=True,
            requires_confirmation=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required to write to vault")

        file_id = params.get("file_id")
        filename = params.get("filename")
        content = params.get("content", "")
        folder_id = params.get("folder_id")

        if not file_id and not filename:
            return ToolResult(success=False, error="Either file_id or filename is required")

        if len(content) > 1024 * 1024:  # 1MB limit for tool writes
            return ToolResult(success=False, error="Content exceeds 1MB limit")

        try:
            from app.models.file import File, Folder, get_file_type
            from app.models.user import User
            from app.database import async_session
            from app.config import get_settings
            from pathlib import Path
            from uuid import uuid4
            from datetime import datetime
            import hashlib

            settings = get_settings()

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Get user for quota check
                user_result = await db.execute(
                    select(User).where(User.id == user_uuid)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    return ToolResult(success=False, error="User not found")

                content_bytes = content.encode("utf-8")
                content_size = len(content_bytes)
                checksum = hashlib.sha256(content_bytes).hexdigest()

                if file_id:
                    # Update existing file
                    file_uuid = UUID(file_id)
                    file_result = await db.execute(
                        select(File).where(
                            File.id == file_uuid,
                            File.user_id == user_uuid
                        )
                    )
                    file = file_result.scalar_one_or_none()

                    if not file:
                        return ToolResult(success=False, error=f"File not found: {file_id}")

                    if file.file_type not in ("document", "code", "data"):
                        return ToolResult(success=False, error="Cannot write to binary files")

                    # Check quota for size increase
                    size_delta = content_size - file.size_bytes
                    if size_delta > 0:
                        user_settings = user.settings or {}
                        used = user_settings.get("storage_used_bytes", 0)
                        quota = user_settings.get("storage_quota_bytes", settings.default_quota_bytes)
                        if used + size_delta > quota:
                            return ToolResult(success=False, error="Storage quota exceeded")

                    # Write content
                    file_path = Path(file.storage_path)
                    file_path.write_text(content, encoding="utf-8")

                    # Update metadata
                    file.size_bytes = content_size
                    file.checksum = checksum
                    file.updated_at = datetime.utcnow()

                    # Update user storage
                    if size_delta != 0:
                        user_settings = user.settings or {}
                        user_settings["storage_used_bytes"] = user_settings.get("storage_used_bytes", 0) + size_delta
                        user.settings = user_settings

                    await db.commit()

                    return ToolResult(
                        success=True,
                        result={
                            "action": "updated",
                            "file_id": str(file.id),
                            "filename": file.name,
                            "size": content_size,
                            "size_human": _format_size(content_size),
                        },
                    )

                else:
                    # Create new file
                    # Validate folder if specified
                    if folder_id:
                        folder_uuid = UUID(folder_id)
                        folder_result = await db.execute(
                            select(Folder).where(
                                Folder.id == folder_uuid,
                                Folder.user_id == user_uuid
                            )
                        )
                        if not folder_result.scalar_one_or_none():
                            return ToolResult(success=False, error=f"Folder not found: {folder_id}")

                    # Check quota
                    user_settings = user.settings or {}
                    used = user_settings.get("storage_used_bytes", 0)
                    quota = user_settings.get("storage_quota_bytes", settings.default_quota_bytes)
                    if used + content_size > quota:
                        return ToolResult(success=False, error="Storage quota exceeded")

                    # Sanitize filename
                    safe_filename = filename.replace("/", "_").replace("\\", "_")[:255]
                    extension = safe_filename.rsplit(".", 1)[-1] if "." in safe_filename else "txt"
                    file_type = get_file_type(extension)

                    # Create storage path
                    new_file_id = uuid4()
                    vault_path = Path(settings.vault_path) / "users" / str(user_uuid) / "files"
                    file_dir = vault_path / str(new_file_id)
                    file_dir.mkdir(parents=True, exist_ok=True)
                    storage_path = file_dir / safe_filename

                    # Write file
                    storage_path.write_text(content, encoding="utf-8")

                    # Create record
                    new_file = File(
                        id=new_file_id,
                        user_id=user_uuid,
                        folder_id=UUID(folder_id) if folder_id else None,
                        name=safe_filename,
                        original_filename=safe_filename,
                        mime_type="text/plain",
                        file_type=file_type,
                        size_bytes=content_size,
                        storage_path=str(storage_path),
                        checksum=checksum,
                        status="ready",
                    )
                    db.add(new_file)

                    # Update user storage
                    user_settings["storage_used_bytes"] = used + content_size
                    user.settings = user_settings

                    await db.commit()

                    return ToolResult(
                        success=True,
                        result={
                            "action": "created",
                            "file_id": str(new_file_id),
                            "filename": safe_filename,
                            "size": content_size,
                            "size_human": _format_size(content_size),
                        },
                    )

        except Exception as e:
            logger.exception("Vault write error")
            return ToolResult(success=False, error=f"Failed to write file: {str(e)}")


# =============================================================================
# VAULT SEARCH
# =============================================================================

class VaultSearchTool(BaseTool):
    """Search file contents in the vault."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="vault_search",
            description="""Search inside file contents in the user's vault.

Use to:
- Find files containing specific text
- Search code for functions, variables, patterns
- Locate configuration values

Returns matching lines with surrounding context.
Searches text files only (code, documents, data).""",
            category=ToolCategory.FILES,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for",
                    },
                    "file_type": {
                        "type": "string",
                        "enum": ["document", "code", "data"],
                        "description": "Filter by file type",
                    },
                    "folder_id": {
                        "type": "string",
                        "description": "Search only in this folder",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum files to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required to search vault")

        query = params.get("query", "").strip()
        file_type = params.get("file_type")
        folder_id = params.get("folder_id")
        max_results = min(params.get("max_results", 10), 50)

        if not query:
            return ToolResult(success=False, error="Search query is required")

        if len(query) < 2:
            return ToolResult(success=False, error="Query must be at least 2 characters")

        try:
            import re
            from app.models.file import File
            from app.database import async_session
            from pathlib import Path

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Build query
                stmt = (
                    select(File)
                    .where(File.user_id == user_uuid)
                    .where(File.file_type.in_(["document", "code", "data"]))
                    .where(File.is_archived == False)  # noqa: E712
                )

                if file_type:
                    stmt = stmt.where(File.file_type == file_type)

                if folder_id:
                    stmt = stmt.where(File.folder_id == UUID(folder_id))

                stmt = stmt.order_by(File.updated_at.desc())

                result = await db.execute(stmt)
                files = result.scalars().all()

                # Compile pattern
                try:
                    pattern = re.compile(re.escape(query), re.IGNORECASE)
                except re.error:
                    return ToolResult(success=False, error="Invalid search pattern")

                results = []
                files_searched = 0
                total_matches = 0

                for file in files:
                    file_path = Path(file.storage_path)
                    if not file_path.exists():
                        continue

                    files_searched += 1

                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        lines = content.splitlines()
                    except Exception:
                        continue

                    matches = []
                    for i, line in enumerate(lines):
                        if pattern.search(line):
                            # Get context (1 line before/after)
                            context_before = lines[i-1] if i > 0 else ""
                            context_after = lines[i+1] if i < len(lines) - 1 else ""

                            matches.append({
                                "line": i + 1,
                                "content": line[:500],  # Truncate long lines
                                "context_before": context_before[:200],
                                "context_after": context_after[:200],
                            })

                            if len(matches) >= 5:  # Max 5 matches per file
                                break

                    if matches:
                        total_matches += len(matches)
                        results.append({
                            "file_id": str(file.id),
                            "filename": file.name,
                            "file_type": file.file_type,
                            "match_count": len(matches),
                            "matches": matches,
                        })

                        if len(results) >= max_results:
                            break

                return ToolResult(
                    success=True,
                    result={
                        "query": query,
                        "files_searched": files_searched,
                        "files_matched": len(results),
                        "total_matches": total_matches,
                        "results": results,
                    },
                )

        except Exception as e:
            logger.exception("Vault search error")
            return ToolResult(success=False, error=f"Search failed: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

# Register all vault tools - Tier 3 complete!
registry.register(VaultListTool())
registry.register(VaultReadTool())
registry.register(VaultInfoTool())
registry.register(VaultWriteTool())
registry.register(VaultSearchTool())
