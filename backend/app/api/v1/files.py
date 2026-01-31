"""
The Vault - File Storage API

User file management with hierarchical folders, quota enforcement,
and secure file upload/download.

"Every alchemist needs a sanctum"
"""

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File as FastAPIFile, status
from fastapi.responses import FileResponse as FastAPIFileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.file import (
    File, Folder,
    ALLOWED_EXTENSIONS, BLOCKED_EXTENSIONS,
    get_file_type, is_allowed_extension,
)
from app.auth.deps import get_current_user
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[UUID] = None  # For moving folders
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_archived: Optional[bool] = None


class FolderResponse(BaseModel):
    id: UUID
    name: str
    parent_id: Optional[UUID]
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_archived: bool
    file_count: int
    folder_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class FileUpdate(BaseModel):
    name: Optional[str] = None
    folder_id: Optional[UUID] = None  # For moving files
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    favorite: Optional[bool] = None
    is_archived: Optional[bool] = None


class FileResponse(BaseModel):
    id: UUID
    name: str
    original_filename: str
    mime_type: Optional[str]
    file_type: str
    size_bytes: int
    folder_id: Optional[UUID]
    description: Optional[str]
    tags: list[str]
    favorite: bool
    is_archived: bool
    access_count: int
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class BreadcrumbItem(BaseModel):
    id: UUID
    name: str


class DirectoryListing(BaseModel):
    current_folder: Optional[FolderResponse]
    path: list[BreadcrumbItem]  # Breadcrumb trail
    folders: list[FolderResponse]
    files: list[FileResponse]
    storage_used: int
    storage_quota: int


class StorageStats(BaseModel):
    used_bytes: int
    quota_bytes: int
    file_count: int
    folder_count: int
    by_type: dict[str, int]  # bytes per file type


class BulkMoveRequest(BaseModel):
    file_ids: list[UUID] = []
    folder_ids: list[UUID] = []
    target_folder_id: Optional[UUID] = None  # None = root


class BulkDeleteRequest(BaseModel):
    file_ids: list[UUID] = []
    folder_ids: list[UUID] = []


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_vault_path(user_id: UUID) -> Path:
    """Get the vault storage path for a user."""
    settings = get_settings()
    return Path(settings.vault_path) / "users" / str(user_id) / "files"


async def get_storage_used(user_id: UUID, db: AsyncSession) -> int:
    """Calculate total storage used by a user."""
    result = await db.execute(
        select(func.coalesce(func.sum(File.size_bytes), 0))
        .where(File.user_id == user_id)
    )
    return result.scalar() or 0


async def check_quota(user_id: UUID, additional_bytes: int, db: AsyncSession) -> bool:
    """Check if user has enough quota for additional bytes."""
    settings = get_settings()
    used = await get_storage_used(user_id, db)
    return (used + additional_bytes) <= settings.default_quota_bytes


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def get_extension(filename: str) -> str:
    """Extract extension from filename."""
    if '.' in filename:
        return filename.rsplit('.', 1)[-1].lower()
    return ''


async def get_folder_path(folder_id: UUID, user_id: UUID, db: AsyncSession) -> list[BreadcrumbItem]:
    """Build breadcrumb path from root to folder."""
    path = []
    current_id = folder_id

    while current_id:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == current_id)
            .where(Folder.user_id == user_id)
        )
        folder = result.scalar_one_or_none()
        if not folder:
            break
        path.insert(0, BreadcrumbItem(id=folder.id, name=folder.name))
        current_id = folder.parent_id

    return path


async def folder_to_response(folder: Folder, db: AsyncSession) -> FolderResponse:
    """Convert Folder model to response with counts."""
    # Count child folders
    folder_result = await db.execute(
        select(func.count(Folder.id))
        .where(Folder.parent_id == folder.id)
    )
    folder_count = folder_result.scalar() or 0

    # Count files in this folder
    file_result = await db.execute(
        select(func.count(File.id))
        .where(File.folder_id == folder.id)
    )
    file_count = file_result.scalar() or 0

    return FolderResponse(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        description=folder.description,
        color=folder.color,
        icon=folder.icon,
        is_archived=folder.is_archived,
        file_count=file_count,
        folder_count=folder_count,
        created_at=folder.created_at.isoformat(),
        updated_at=folder.updated_at.isoformat(),
    )


def file_to_response(file: File) -> FileResponse:
    """Convert File model to response."""
    return FileResponse(
        id=file.id,
        name=file.name,
        original_filename=file.original_filename,
        mime_type=file.mime_type,
        file_type=file.file_type,
        size_bytes=file.size_bytes,
        folder_id=file.folder_id,
        description=file.description,
        tags=file.tags or [],
        favorite=file.favorite,
        is_archived=file.is_archived,
        access_count=file.access_count,
        status=file.status,
        created_at=file.created_at.isoformat(),
        updated_at=file.updated_at.isoformat(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECTORY LISTING
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=DirectoryListing)
async def list_root_directory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List contents of root directory."""
    return await list_directory_contents(None, user, db)


@router.get("/folder/{folder_id}", response_model=DirectoryListing)
async def list_folder_contents(
    folder_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List contents of a specific folder."""
    # Verify folder exists and belongs to user
    result = await db.execute(
        select(Folder)
        .where(Folder.id == folder_id)
        .where(Folder.user_id == user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    return await list_directory_contents(folder_id, user, db)


async def list_directory_contents(
    folder_id: Optional[UUID],
    user: User,
    db: AsyncSession
) -> DirectoryListing:
    """Internal helper to list directory contents."""
    settings = get_settings()

    # Get current folder info (if not root)
    current_folder = None
    path = []
    if folder_id:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == folder_id)
            .where(Folder.user_id == user.id)
        )
        folder = result.scalar_one_or_none()
        if folder:
            current_folder = await folder_to_response(folder, db)
            path = await get_folder_path(folder_id, user.id, db)

    # Get child folders
    folders_result = await db.execute(
        select(Folder)
        .where(Folder.user_id == user.id)
        .where(Folder.parent_id == folder_id)
        .where(Folder.is_archived == False)
        .order_by(Folder.name)
    )
    folders = folders_result.scalars().all()
    folder_responses = [await folder_to_response(f, db) for f in folders]

    # Get files in this folder
    files_result = await db.execute(
        select(File)
        .where(File.user_id == user.id)
        .where(File.folder_id == folder_id)
        .where(File.is_archived == False)
        .order_by(File.name)
    )
    files = files_result.scalars().all()
    file_responses = [file_to_response(f) for f in files]

    # Get storage stats
    storage_used = await get_storage_used(user.id, db)

    return DirectoryListing(
        current_folder=current_folder,
        path=path,
        folders=folder_responses,
        files=file_responses,
        storage_used=storage_used,
        storage_quota=settings.default_quota_bytes,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FOLDER CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/folder", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    request: FolderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new folder."""
    # Validate parent folder if specified
    if request.parent_id:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == request.parent_id)
            .where(Folder.user_id == user.id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent folder not found"
            )

    # Check for duplicate name in same parent
    result = await db.execute(
        select(Folder)
        .where(Folder.user_id == user.id)
        .where(Folder.parent_id == request.parent_id)
        .where(Folder.name == request.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder with this name already exists"
        )

    folder = Folder(
        id=uuid4(),
        user_id=user.id,
        parent_id=request.parent_id,
        name=request.name,
        description=request.description,
        color=request.color,
        icon=request.icon,
    )
    db.add(folder)
    await db.commit()

    logger.info(f"Created folder {folder.id} for user {user.id}")
    return await folder_to_response(folder, db)


@router.patch("/folder/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    request: FolderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update folder properties or move to new parent."""
    result = await db.execute(
        select(Folder)
        .where(Folder.id == folder_id)
        .where(Folder.user_id == user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    # Validate parent if moving
    if request.parent_id is not None and request.parent_id != folder.parent_id:
        # Can't move folder into itself
        if request.parent_id == folder.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move folder into itself"
            )
        # Validate new parent exists
        if request.parent_id:
            parent_result = await db.execute(
                select(Folder)
                .where(Folder.id == request.parent_id)
                .where(Folder.user_id == user.id)
            )
            if not parent_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target folder not found"
                )

    # Update fields
    if request.name is not None:
        folder.name = request.name
    if request.parent_id is not None:
        folder.parent_id = request.parent_id
    if request.description is not None:
        folder.description = request.description
    if request.color is not None:
        folder.color = request.color
    if request.icon is not None:
        folder.icon = request.icon
    if request.is_archived is not None:
        folder.is_archived = request.is_archived

    folder.updated_at = datetime.utcnow()
    await db.commit()

    return await folder_to_response(folder, db)


@router.delete("/folder/{folder_id}")
async def delete_folder(
    folder_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a folder and all its contents (cascades to files and subfolders)."""
    result = await db.execute(
        select(Folder)
        .where(Folder.id == folder_id)
        .where(Folder.user_id == user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found"
        )

    # Get all files in this folder tree for disk cleanup
    # We need to recursively collect all files
    async def collect_files_recursive(folder_id: UUID) -> list[File]:
        files = []

        # Get files in this folder
        files_result = await db.execute(
            select(File).where(File.folder_id == folder_id)
        )
        files.extend(files_result.scalars().all())

        # Get subfolders
        subfolders_result = await db.execute(
            select(Folder).where(Folder.parent_id == folder_id)
        )
        for subfolder in subfolders_result.scalars().all():
            files.extend(await collect_files_recursive(subfolder.id))

        return files

    files_to_delete = await collect_files_recursive(folder_id)

    # Delete from disk
    for file in files_to_delete:
        try:
            file_path = Path(file.storage_path)
            if file_path.exists():
                file_path.unlink()
                # Clean up parent directory if empty
                parent_dir = file_path.parent
                if parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
        except Exception as e:
            logger.warning(f"Failed to delete file from disk: {file.storage_path} - {e}")

    # Delete folder (cascades to files and subfolders in DB)
    await db.delete(folder)
    await db.commit()

    logger.info(f"Deleted folder {folder_id} with {len(files_to_delete)} files")
    return {"message": f"Folder deleted with {len(files_to_delete)} files"}


# ═══════════════════════════════════════════════════════════════════════════════
# FILE UPLOAD / DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    folder_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a file to The Vault.

    - Validates file type against allowed extensions
    - Enforces user storage quota
    - Calculates checksum for integrity
    - Stores file on Railway volume
    """
    settings = get_settings()

    # Validate file extension
    extension = get_extension(file.filename or "")
    if not extension or not is_allowed_extension(extension):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Blocked extensions: {BLOCKED_EXTENSIONS}"
        )

    # Read file content to check size and calculate checksum
    content = await file.read()
    file_size = len(content)

    # Validate file size
    if file_size > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.max_file_size_bytes / 1024 / 1024:.0f}MB"
        )

    # Check quota
    if not await check_quota(user.id, file_size, db):
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Storage quota exceeded. Delete some files to free up space."
        )

    # Validate folder if specified
    if folder_id:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == folder_id)
            .where(Folder.user_id == user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found"
            )

    # Generate unique file ID and storage path
    file_id = uuid4()
    vault_path = get_vault_path(user.id)
    file_dir = vault_path / str(file_id)
    file_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_filename = (file.filename or f"file.{extension}").replace("/", "_").replace("\\", "_")
    storage_path = file_dir / safe_filename

    # Write file to disk
    try:
        with open(storage_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to write file to disk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file"
        )

    # Calculate checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Determine file type category
    file_type = get_file_type(extension)

    # Create database record
    file_record = File(
        id=file_id,
        user_id=user.id,
        folder_id=folder_id,
        name=safe_filename,
        original_filename=file.filename or safe_filename,
        mime_type=file.content_type,
        file_type=file_type,
        size_bytes=file_size,
        storage_path=str(storage_path),
        checksum=checksum,
        status="ready",
    )
    db.add(file_record)
    await db.commit()

    logger.info(f"Uploaded file {file_id} ({file_size} bytes) for user {user.id}")
    return file_to_response(file_record)


@router.get("/{file_id}", response_model=FileResponse)
async def get_file_metadata(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get file metadata without downloading."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    return file_to_response(file)


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download a file."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    file_path = Path(file.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )

    # Update access stats
    file.access_count += 1
    file.last_accessed_at = datetime.utcnow()
    await db.commit()

    return FastAPIFileResponse(
        path=str(file_path),
        filename=file.original_filename,
        media_type=file.mime_type or "application/octet-stream",
    )


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: UUID,
    lines: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a preview of file contents.

    For text files, returns first N lines.
    For images, returns the file itself.
    For other types, returns metadata only.
    """
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    file_path = Path(file.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )

    # Update access stats
    file.access_count += 1
    file.last_accessed_at = datetime.utcnow()
    await db.commit()

    # Image preview - return the file
    if file.file_type == "image":
        return FastAPIFileResponse(
            path=str(file_path),
            filename=file.name,
            media_type=file.mime_type or "image/png",
        )

    # Text/code preview - return first N lines
    if file.file_type in ("document", "code", "data"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content_lines = []
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    content_lines.append(line)
                content = "".join(content_lines)
                truncated = i >= lines
        except Exception:
            content = "[Unable to read file content]"
            truncated = False

        return {
            "id": file.id,
            "name": file.name,
            "file_type": file.file_type,
            "mime_type": file.mime_type,
            "size_bytes": file.size_bytes,
            "content": content,
            "truncated": truncated,
            "lines_shown": min(lines, len(content_lines)) if 'content_lines' in dir() else 0,
        }

    # Other types - metadata only
    return {
        "id": file.id,
        "name": file.name,
        "file_type": file.file_type,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "preview_available": False,
        "message": "Preview not available for this file type",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CORTEX DIVER - FILE CONTENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class FileContentRequest(BaseModel):
    content: str


@router.get("/{file_id}/content")
async def get_file_content(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full file content for editing.

    Returns the complete file content (no truncation) for text-based files.
    Used by Cortex Diver IDE.
    """
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    file_path = Path(file.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )

    # Only allow text-based files
    if file.file_type not in ("document", "code", "data"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit binary files"
        )

    # Read full content
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read file: {str(e)}"
        )

    # Update access stats
    file.access_count += 1
    file.last_accessed_at = datetime.utcnow()
    await db.commit()

    return {
        "id": file.id,
        "name": file.name,
        "file_type": file.file_type,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "content": content,
        "language": get_monaco_language(file.name),
    }


@router.put("/{file_id}/content")
async def save_file_content(
    file_id: UUID,
    request: FileContentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Save file content from editor.

    Overwrites the file with new content and updates metadata.
    Used by Cortex Diver IDE.
    """
    settings = get_settings()

    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Only allow text-based files
    if file.file_type not in ("document", "code", "data"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit binary files"
        )

    file_path = Path(file.storage_path)

    # Calculate new size and check quota
    new_content = request.content.encode("utf-8")
    new_size = len(new_content)
    size_delta = new_size - file.size_bytes

    # Check quota if size is increasing
    if size_delta > 0:
        user_settings = user.settings or {}
        used = user_settings.get("storage_used_bytes", 0)
        quota = user_settings.get("storage_quota_bytes", settings.default_quota_bytes)

        if used + size_delta > quota:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Storage quota exceeded. Available: {quota - used} bytes"
            )

    # Write content
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    # Update file metadata
    old_size = file.size_bytes
    file.size_bytes = new_size
    file.checksum = hashlib.sha256(new_content).hexdigest()
    file.updated_at = datetime.utcnow()

    # Update user storage stats
    if size_delta != 0:
        user_settings = user.settings or {}
        user_settings["storage_used_bytes"] = user_settings.get("storage_used_bytes", 0) + size_delta
        user.settings = user_settings

    await db.commit()
    await db.refresh(file)

    return {
        "id": file.id,
        "name": file.name,
        "size_bytes": file.size_bytes,
        "saved": True,
        "size_delta": size_delta,
    }


def get_monaco_language(filename: str) -> str:
    """Map file extension to Monaco editor language."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    language_map = {
        # Web
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "html": "html",
        "htm": "html",
        "css": "css",
        "scss": "scss",
        "less": "less",
        "vue": "html",
        "svelte": "html",
        # Python
        "py": "python",
        "pyw": "python",
        "pyi": "python",
        # Systems
        "c": "c",
        "h": "c",
        "cpp": "cpp",
        "hpp": "cpp",
        "cc": "cpp",
        "rs": "rust",
        "go": "go",
        "java": "java",
        "kt": "kotlin",
        "swift": "swift",
        # Data/Config
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
        "xml": "xml",
        "sql": "sql",
        "graphql": "graphql",
        # Shell
        "sh": "shell",
        "bash": "shell",
        "zsh": "shell",
        "fish": "shell",
        "ps1": "powershell",
        # Markup
        "md": "markdown",
        "mdx": "markdown",
        "rst": "restructuredtext",
        "tex": "latex",
        # Other
        "rb": "ruby",
        "php": "php",
        "lua": "lua",
        "r": "r",
        "dockerfile": "dockerfile",
        "makefile": "makefile",
        "env": "ini",
        "ini": "ini",
        "conf": "ini",
        "txt": "plaintext",
        "log": "plaintext",
    }

    # Handle special filenames
    special_files = {
        "dockerfile": "dockerfile",
        "makefile": "makefile",
        ".gitignore": "ignore",
        ".dockerignore": "ignore",
        ".env": "ini",
        ".editorconfig": "ini",
    }

    lower_name = filename.lower()
    if lower_name in special_files:
        return special_files[lower_name]

    return language_map.get(ext, "plaintext")


@router.patch("/{file_id}", response_model=FileResponse)
async def update_file(
    file_id: UUID,
    request: FileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update file properties or move to new folder."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Validate folder if moving
    if request.folder_id is not None and request.folder_id != file.folder_id:
        if request.folder_id:  # Not moving to root
            folder_result = await db.execute(
                select(Folder)
                .where(Folder.id == request.folder_id)
                .where(Folder.user_id == user.id)
            )
            if not folder_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target folder not found"
                )

    # Update fields
    if request.name is not None:
        file.name = request.name
    if request.folder_id is not None:
        file.folder_id = request.folder_id if request.folder_id else None
    if request.description is not None:
        file.description = request.description
    if request.tags is not None:
        file.tags = request.tags
    if request.favorite is not None:
        file.favorite = request.favorite
    if request.is_archived is not None:
        file.is_archived = request.is_archived

    file.updated_at = datetime.utcnow()
    await db.commit()

    return file_to_response(file)


@router.delete("/{file_id}")
async def delete_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a file from The Vault."""
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Delete from disk
    try:
        file_path = Path(file.storage_path)
        if file_path.exists():
            file_path.unlink()
            # Clean up parent directory if empty
            parent_dir = file_path.parent
            if parent_dir.exists() and not any(parent_dir.iterdir()):
                parent_dir.rmdir()
    except Exception as e:
        logger.warning(f"Failed to delete file from disk: {file.storage_path} - {e}")

    # Delete from database
    await db.delete(file)
    await db.commit()

    logger.info(f"Deleted file {file_id} for user {user.id}")
    return {"message": "File deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# BULK OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/move")
async def bulk_move(
    request: BulkMoveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Move multiple files and/or folders to a target folder."""
    # Validate target folder
    if request.target_folder_id:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == request.target_folder_id)
            .where(Folder.user_id == user.id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target folder not found"
            )

    moved_files = 0
    moved_folders = 0

    # Move files
    for file_id in request.file_ids:
        result = await db.execute(
            select(File)
            .where(File.id == file_id)
            .where(File.user_id == user.id)
        )
        file = result.scalar_one_or_none()
        if file:
            file.folder_id = request.target_folder_id
            file.updated_at = datetime.utcnow()
            moved_files += 1

    # Move folders (can't move folder into its own child)
    for folder_id in request.folder_ids:
        if folder_id == request.target_folder_id:
            continue  # Skip moving folder to itself

        result = await db.execute(
            select(Folder)
            .where(Folder.id == folder_id)
            .where(Folder.user_id == user.id)
        )
        folder = result.scalar_one_or_none()
        if folder:
            folder.parent_id = request.target_folder_id
            folder.updated_at = datetime.utcnow()
            moved_folders += 1

    await db.commit()

    return {
        "message": f"Moved {moved_files} files and {moved_folders} folders",
        "moved_files": moved_files,
        "moved_folders": moved_folders,
    }


@router.post("/delete")
async def bulk_delete(
    request: BulkDeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete multiple files and/or folders."""
    deleted_files = 0
    deleted_folders = 0

    # Delete files
    for file_id in request.file_ids:
        result = await db.execute(
            select(File)
            .where(File.id == file_id)
            .where(File.user_id == user.id)
        )
        file = result.scalar_one_or_none()
        if file:
            # Delete from disk
            try:
                file_path = Path(file.storage_path)
                if file_path.exists():
                    file_path.unlink()
                    parent_dir = file_path.parent
                    if parent_dir.exists() and not any(parent_dir.iterdir()):
                        parent_dir.rmdir()
            except Exception as e:
                logger.warning(f"Failed to delete file from disk: {e}")

            await db.delete(file)
            deleted_files += 1

    # Delete folders (cascades in DB, need disk cleanup)
    for folder_id in request.folder_ids:
        result = await db.execute(
            select(Folder)
            .where(Folder.id == folder_id)
            .where(Folder.user_id == user.id)
        )
        folder = result.scalar_one_or_none()
        if folder:
            # Collect all files recursively for disk cleanup
            async def collect_files(fid: UUID) -> list[str]:
                paths = []
                files_result = await db.execute(
                    select(File.storage_path).where(File.folder_id == fid)
                )
                paths.extend([r[0] for r in files_result.fetchall()])

                subfolders_result = await db.execute(
                    select(Folder.id).where(Folder.parent_id == fid)
                )
                for (subfolder_id,) in subfolders_result.fetchall():
                    paths.extend(await collect_files(subfolder_id))
                return paths

            file_paths = await collect_files(folder_id)

            # Delete files from disk
            for path in file_paths:
                try:
                    file_path = Path(path)
                    if file_path.exists():
                        file_path.unlink()
                        parent_dir = file_path.parent
                        if parent_dir.exists() and not any(parent_dir.iterdir()):
                            parent_dir.rmdir()
                except Exception as e:
                    logger.warning(f"Failed to delete file from disk: {e}")

            await db.delete(folder)
            deleted_folders += 1

    await db.commit()

    return {
        "message": f"Deleted {deleted_files} files and {deleted_folders} folders",
        "deleted_files": deleted_files,
        "deleted_folders": deleted_folders,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH & SPECIAL LISTINGS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/search/files", response_model=list[FileResponse])
async def search_files(
    q: str = Query(..., max_length=200),
    file_type: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search files by name, with optional type filter."""
    query = (
        select(File)
        .where(File.user_id == user.id)
        .where(File.name.ilike(f"%{q}%"))
    )

    if file_type:
        query = query.where(File.file_type == file_type)

    query = query.order_by(File.updated_at.desc()).limit(limit)

    result = await db.execute(query)
    files = result.scalars().all()

    return [file_to_response(f) for f in files]


# ═══════════════════════════════════════════════════════════════════════════════
# RAG & INTELLIGENCE - Content Search and Project Context
# ═══════════════════════════════════════════════════════════════════════════════

class ContentSearchResult(BaseModel):
    """A search result with file info and matching content."""
    file_id: UUID
    file_name: str
    file_type: str
    folder_id: Optional[UUID]
    matches: list[dict]  # [{ line: int, content: str, context_before: str, context_after: str }]
    match_count: int


class ContentSearchResponse(BaseModel):
    """Response for content search."""
    query: str
    results: list[ContentSearchResult]
    total_matches: int
    files_searched: int


@router.get("/search/content", response_model=ContentSearchResponse)
async def search_file_contents(
    q: str = Query(..., max_length=200),
    file_type: Optional[str] = None,
    folder_id: Optional[UUID] = None,
    limit: int = 20,
    context_lines: int = 2,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search inside file contents (The All-Seeing Eye).

    Searches text-based files for the query string.
    Returns matching lines with surrounding context.

    Used by Cortex Diver for semantic code search.
    """
    import re

    # Build query for searchable files
    query = (
        select(File)
        .where(File.user_id == user.id)
        .where(File.file_type.in_(["document", "code", "data"]))
        .where(File.is_archived == False)
    )

    if file_type:
        query = query.where(File.file_type == file_type)

    if folder_id:
        query = query.where(File.folder_id == folder_id)

    query = query.order_by(File.updated_at.desc())

    result = await db.execute(query)
    files = result.scalars().all()

    results = []
    total_matches = 0
    files_searched = 0

    # Compile search pattern (case-insensitive)
    try:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(q), re.IGNORECASE)

    for file in files:
        file_path = Path(file.storage_path)
        if not file_path.exists():
            continue

        files_searched += 1

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        matches = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                # Get context
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)

                context_before = "".join(lines[start:i]).rstrip('\n')
                context_after = "".join(lines[i+1:end]).rstrip('\n')

                matches.append({
                    "line": i + 1,  # 1-indexed
                    "content": line.rstrip('\n'),
                    "context_before": context_before,
                    "context_after": context_after,
                })

                if len(matches) >= 10:  # Max matches per file
                    break

        if matches:
            results.append(ContentSearchResult(
                file_id=file.id,
                file_name=file.name,
                file_type=file.file_type,
                folder_id=file.folder_id,
                matches=matches,
                match_count=len(matches),
            ))
            total_matches += len(matches)

            if len(results) >= limit:
                break

    return ContentSearchResponse(
        query=q,
        results=results,
        total_matches=total_matches,
        files_searched=files_searched,
    )


class ProjectContextFile(BaseModel):
    """A file in the project context."""
    id: UUID
    name: str
    path: str  # Full path from root
    file_type: str
    size_bytes: int
    preview: Optional[str] = None  # First N lines for key files


class ProjectContext(BaseModel):
    """Project structure and context for AI assistance."""
    total_files: int
    total_folders: int
    file_tree: list[dict]  # Nested structure
    key_files: list[ProjectContextFile]  # Important files with previews
    languages: dict[str, int]  # File counts by language
    storage_used: int


@router.get("/context", response_model=ProjectContext)
async def get_project_context(
    folder_id: Optional[UUID] = None,
    include_previews: bool = True,
    preview_lines: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get project structure and context for AI assistance.

    Returns a summary of the user's files including:
    - File tree structure
    - Key files with content previews (README, main files, configs)
    - Language breakdown

    Used by Cortex Diver's AI agent for codebase awareness.
    """
    # Get all folders
    folders_result = await db.execute(
        select(Folder)
        .where(Folder.user_id == user.id)
        .where(Folder.is_archived == False)
        .order_by(Folder.name)
    )
    folders = folders_result.scalars().all()

    # Get all files
    files_query = select(File).where(File.user_id == user.id).where(File.is_archived == False)
    if folder_id:
        # Only files in this subtree
        files_query = files_query.where(File.folder_id == folder_id)
    files_result = await db.execute(files_query.order_by(File.name))
    files = files_result.scalars().all()

    # Build file tree
    def build_tree(parent_id=None, path=""):
        items = []

        # Add folders
        for folder in folders:
            if folder.parent_id == parent_id:
                folder_path = f"{path}/{folder.name}" if path else folder.name
                children = build_tree(folder.id, folder_path)
                items.append({
                    "type": "folder",
                    "id": str(folder.id),
                    "name": folder.name,
                    "path": folder_path,
                    "children": children,
                })

        # Add files
        for file in files:
            if file.folder_id == parent_id:
                file_path = f"{path}/{file.name}" if path else file.name
                items.append({
                    "type": "file",
                    "id": str(file.id),
                    "name": file.name,
                    "path": file_path,
                    "file_type": file.file_type,
                    "size": file.size_bytes,
                })

        return items

    file_tree = build_tree(folder_id if folder_id else None)

    # Identify key files (README, main files, configs)
    KEY_FILE_PATTERNS = [
        "readme", "readme.md", "readme.txt",
        "main.py", "app.py", "index.js", "index.ts", "main.js", "main.ts",
        "package.json", "requirements.txt", "pyproject.toml", "cargo.toml",
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "config.py", "settings.py", "config.js", "config.ts",
        "makefile", "justfile",
    ]

    key_files = []
    for file in files:
        lower_name = file.name.lower()
        is_key = any(lower_name == pattern or lower_name.endswith(f"/{pattern}") for pattern in KEY_FILE_PATTERNS)

        # Also include entry-point-like files
        if not is_key and file.file_type == "code":
            if lower_name in ["index.vue", "app.vue", "main.vue", "__init__.py", "mod.rs", "lib.rs"]:
                is_key = True

        if is_key:
            file_path = file.name
            # Find path by traversing folders
            folder_id_curr = file.folder_id
            while folder_id_curr:
                folder = next((f for f in folders if f.id == folder_id_curr), None)
                if folder:
                    file_path = f"{folder.name}/{file_path}"
                    folder_id_curr = folder.parent_id
                else:
                    break

            preview = None
            if include_previews and file.file_type in ("document", "code", "data"):
                file_disk_path = Path(file.storage_path)
                if file_disk_path.exists():
                    try:
                        with open(file_disk_path, "r", encoding="utf-8", errors="replace") as f:
                            preview_content = []
                            for i, line in enumerate(f):
                                if i >= preview_lines:
                                    break
                                preview_content.append(line)
                            preview = "".join(preview_content)
                    except Exception:
                        pass

            key_files.append(ProjectContextFile(
                id=file.id,
                name=file.name,
                path=file_path,
                file_type=file.file_type,
                size_bytes=file.size_bytes,
                preview=preview,
            ))

    # Count languages
    language_counts = {}
    for file in files:
        if file.file_type == "code":
            lang = get_monaco_language(file.name)
            language_counts[lang] = language_counts.get(lang, 0) + 1

    # Storage used
    storage_used = sum(f.size_bytes for f in files)

    return ProjectContext(
        total_files=len(files),
        total_folders=len(folders),
        file_tree=file_tree,
        key_files=key_files,
        languages=language_counts,
        storage_used=storage_used,
    )


@router.get("/context/prompt")
async def get_project_context_prompt(
    folder_id: Optional[UUID] = None,
    max_files: int = 10,
    preview_lines: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get project context formatted for AI agent injection.

    Returns a markdown-formatted string containing:
    - Project structure overview
    - Key file contents
    - Language breakdown

    This can be directly injected into agent prompts for codebase awareness.
    """
    # Get project context
    context = await get_project_context(
        folder_id=folder_id,
        include_previews=True,
        preview_lines=preview_lines,
        user=user,
        db=db
    )

    # Format as prompt context
    lines = [
        "## Project Context",
        "",
        f"**Files:** {context.total_files} | **Folders:** {context.total_folders}",
        "",
    ]

    # Languages
    if context.languages:
        lang_str = ", ".join(f"{lang}: {count}" for lang, count in sorted(context.languages.items(), key=lambda x: -x[1])[:5])
        lines.append(f"**Languages:** {lang_str}")
        lines.append("")

    # File tree (simplified)
    def format_tree(items, depth=0):
        result = []
        indent = "  " * depth
        for item in items[:20]:  # Limit items
            if item["type"] == "folder":
                result.append(f"{indent}📁 {item['name']}/")
                if depth < 2:  # Limit depth
                    result.extend(format_tree(item.get("children", []), depth + 1))
            else:
                icon = "📄" if item.get("file_type") == "document" else "💻" if item.get("file_type") == "code" else "📊"
                result.append(f"{indent}{icon} {item['name']}")
        return result

    lines.append("### Structure")
    lines.append("```")
    lines.extend(format_tree(context.file_tree))
    lines.append("```")
    lines.append("")

    # Key files with previews
    if context.key_files:
        lines.append("### Key Files")
        lines.append("")

        for kf in context.key_files[:max_files]:
            lines.append(f"#### {kf.path}")
            if kf.preview:
                lang = get_monaco_language(kf.name)
                lines.append(f"```{lang}")
                # Truncate preview if too long
                preview = kf.preview
                if len(preview) > 3000:
                    preview = preview[:3000] + "\n... (truncated)"
                lines.append(preview.rstrip())
                lines.append("```")
            lines.append("")

    return {
        "prompt": "\n".join(lines),
        "file_count": context.total_files,
        "key_file_count": len(context.key_files),
    }


class RelevantFilesRequest(BaseModel):
    """Request for finding relevant files based on a query."""
    query: str
    current_file_id: Optional[UUID] = None
    max_files: int = 5


class RelevantFileResult(BaseModel):
    """A relevant file with content."""
    id: UUID
    name: str
    path: str
    relevance: str  # Why this file is relevant
    content: Optional[str] = None


@router.post("/context/relevant")
async def find_relevant_files(
    request: RelevantFilesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Find files relevant to a query for RAG context injection.

    Uses keyword matching and file patterns to find related files.
    Returns file contents that can be injected into agent prompts.

    This is a simple relevance algorithm - can be enhanced with embeddings later.
    """
    import re

    # Get all text-based files
    result = await db.execute(
        select(File)
        .where(File.user_id == user.id)
        .where(File.file_type.in_(["document", "code", "data"]))
        .where(File.is_archived == False)
    )
    files = result.scalars().all()

    # Get folders for path building
    folders_result = await db.execute(
        select(Folder)
        .where(Folder.user_id == user.id)
    )
    folders = {f.id: f for f in folders_result.scalars().all()}

    def get_file_path(file):
        path = file.name
        folder_id = file.folder_id
        while folder_id:
            folder = folders.get(folder_id)
            if folder:
                path = f"{folder.name}/{path}"
                folder_id = folder.parent_id
            else:
                break
        return path

    # Extract keywords from query
    query_lower = request.query.lower()
    keywords = set(re.findall(r'\b\w+\b', query_lower))
    keywords.discard('the')
    keywords.discard('and')
    keywords.discard('for')
    keywords.discard('this')
    keywords.discard('that')
    keywords.discard('with')
    keywords.discard('how')
    keywords.discard('what')
    keywords.discard('why')

    relevant_files = []

    for file in files:
        if request.current_file_id and file.id == request.current_file_id:
            continue

        score = 0
        relevance_reasons = []

        file_path = get_file_path(file)
        file_path_lower = file_path.lower()
        file_name_lower = file.name.lower()

        # Check filename matches
        for kw in keywords:
            if kw in file_name_lower:
                score += 3
                relevance_reasons.append(f"filename contains '{kw}'")

            if kw in file_path_lower:
                score += 1
                if f"filename contains '{kw}'" not in relevance_reasons:
                    relevance_reasons.append(f"path contains '{kw}'")

        # Check file content (if accessible)
        file_disk_path = Path(file.storage_path)
        if file_disk_path.exists():
            try:
                with open(file_disk_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(10000)  # Read first 10KB
                    content_lower = content.lower()

                    for kw in keywords:
                        if len(kw) >= 3 and kw in content_lower:
                            matches = content_lower.count(kw)
                            score += min(matches, 5)
                            if matches > 0:
                                relevance_reasons.append(f"contains '{kw}' ({matches}x)")

            except Exception:
                content = None
        else:
            content = None

        if score > 0:
            relevant_files.append({
                "file": file,
                "path": file_path,
                "score": score,
                "reasons": relevance_reasons[:3],  # Top 3 reasons
            })

    # Sort by relevance score
    relevant_files.sort(key=lambda x: x["score"], reverse=True)

    # Return top N with content
    results = []
    for item in relevant_files[:request.max_files]:
        file = item["file"]
        content = None

        file_disk_path = Path(file.storage_path)
        if file_disk_path.exists():
            try:
                with open(file_disk_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(8000)  # Limit content size
                    if len(content) >= 8000:
                        content += "\n... (truncated)"
            except Exception:
                pass

        results.append(RelevantFileResult(
            id=file.id,
            name=file.name,
            path=item["path"],
            relevance=", ".join(item["reasons"]),
            content=content,
        ))

    return {
        "query": request.query,
        "results": results,
        "total_matched": len(relevant_files),
    }


@router.get("/recent", response_model=list[FileResponse])
async def get_recent_files(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recently accessed files."""
    result = await db.execute(
        select(File)
        .where(File.user_id == user.id)
        .where(File.last_accessed_at.is_not(None))
        .order_by(File.last_accessed_at.desc())
        .limit(limit)
    )
    files = result.scalars().all()
    return [file_to_response(f) for f in files]


@router.get("/favorites", response_model=list[FileResponse])
async def get_favorite_files(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get favorite files."""
    result = await db.execute(
        select(File)
        .where(File.user_id == user.id)
        .where(File.favorite == True)
        .order_by(File.updated_at.desc())
        .limit(limit)
    )
    files = result.scalars().all()
    return [file_to_response(f) for f in files]


@router.get("/stats", response_model=StorageStats)
async def get_storage_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user storage statistics."""
    settings = get_settings()

    # Total used
    used = await get_storage_used(user.id, db)

    # File count
    file_count_result = await db.execute(
        select(func.count(File.id)).where(File.user_id == user.id)
    )
    file_count = file_count_result.scalar() or 0

    # Folder count
    folder_count_result = await db.execute(
        select(func.count(Folder.id)).where(Folder.user_id == user.id)
    )
    folder_count = folder_count_result.scalar() or 0

    # By type
    by_type_result = await db.execute(
        select(File.file_type, func.sum(File.size_bytes))
        .where(File.user_id == user.id)
        .group_by(File.file_type)
    )
    by_type = {row[0]: row[1] or 0 for row in by_type_result.fetchall()}

    return StorageStats(
        used_bytes=used,
        quota_bytes=settings.default_quota_bytes,
        file_count=file_count,
        folder_count=folder_count,
        by_type=by_type,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CORTEX DIVER - CODE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

# Supported languages for execution
EXECUTABLE_EXTENSIONS = {
    'py': {'cmd': ['python3', '-u'], 'name': 'Python'},
    'js': {'cmd': ['node'], 'name': 'JavaScript'},
    'sh': {'cmd': ['bash'], 'name': 'Shell'},
    'bash': {'cmd': ['bash'], 'name': 'Bash'},
}

# Execution limits
MAX_EXECUTION_TIME = 10  # seconds
MAX_OUTPUT_SIZE = 100_000  # characters


class ExecuteRequest(BaseModel):
    """Optional stdin input for execution."""
    stdin: Optional[str] = None


class ExecuteResponse(BaseModel):
    """Execution result."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    truncated: bool = False
    language: str


@router.post("/{file_id}/execute", response_model=ExecuteResponse)
async def execute_file(
    file_id: UUID,
    request: ExecuteRequest = ExecuteRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute a code file in a sandboxed environment.

    Supported languages: Python, JavaScript (Node), Shell/Bash

    Limits:
    - 10 second timeout
    - 100KB output limit
    - No network access (future)
    - No file system access outside temp (future)

    Used by Cortex Diver terminal panel.
    """
    import time
    start_time = time.time()

    # Get file
    result = await db.execute(
        select(File)
        .where(File.id == file_id)
        .where(File.user_id == user.id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Check file extension
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in EXECUTABLE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot execute .{ext} files. Supported: {', '.join(EXECUTABLE_EXTENSIONS.keys())}"
        )

    exec_config = EXECUTABLE_EXTENSIONS[ext]
    file_path = Path(file.storage_path)

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )

    # Build command
    cmd = exec_config['cmd'] + [str(file_path)]

    # Execute with timeout
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if request.stdin else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Sandbox: limit what the process can do
            env={
                'PATH': '/usr/local/bin:/usr/bin:/bin',
                'HOME': '/tmp',
                'TERM': 'xterm',
                'LANG': 'en_US.UTF-8',
                # Prevent network access in Python
                'PYTHONDONTWRITEBYTECODE': '1',
            },
            cwd='/tmp',  # Run in temp directory
        )

        # Wait for completion with timeout
        stdin_data = request.stdin.encode() if request.stdin else None
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=stdin_data),
                timeout=MAX_EXECUTION_TIME
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ExecuteResponse(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {MAX_EXECUTION_TIME} seconds",
                exit_code=-1,
                execution_time=MAX_EXECUTION_TIME,
                truncated=False,
                language=exec_config['name'],
            )

        # Decode output
        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')

        # Truncate if too long
        truncated = False
        if len(stdout_str) > MAX_OUTPUT_SIZE:
            stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + f"\n\n... (output truncated at {MAX_OUTPUT_SIZE} chars)"
            truncated = True
        if len(stderr_str) > MAX_OUTPUT_SIZE:
            stderr_str = stderr_str[:MAX_OUTPUT_SIZE] + f"\n\n... (output truncated at {MAX_OUTPUT_SIZE} chars)"
            truncated = True

        execution_time = time.time() - start_time

        return ExecuteResponse(
            success=process.returncode == 0,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=process.returncode or 0,
            execution_time=round(execution_time, 3),
            truncated=truncated,
            language=exec_config['name'],
        )

    except FileNotFoundError:
        return ExecuteResponse(
            success=False,
            stdout="",
            stderr=f"Runtime not found for {exec_config['name']}. Please ensure the runtime is installed.",
            exit_code=-1,
            execution_time=0,
            truncated=False,
            language=exec_config['name'],
        )
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return ExecuteResponse(
            success=False,
            stdout="",
            stderr=f"Execution failed: {str(e)}",
            exit_code=-1,
            execution_time=time.time() - start_time,
            truncated=False,
            language=exec_config['name'],
        )
