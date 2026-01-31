"""
File Storage Models - The Vault

Hierarchical file storage system for ApexAurum Cloud users.
Supports folders (with nesting) and files with metadata.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Folder(Base):
    """
    User file system folder.

    Supports hierarchical nesting via self-referential parent_id.
    Deleting a folder cascades to all children and files within.
    """

    __tablename__ = "folders"

    # Identity
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Hierarchy (self-referential like Conversation branching)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        index=True,
        nullable=True
    )

    # Content
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Customization
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Organization
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Self-referential relationships (pattern from Conversation)
    parent = relationship(
        "Folder",
        remote_side="Folder.id",
        back_populates="children",
        foreign_keys="[Folder.parent_id]"
    )
    children = relationship(
        "Folder",
        back_populates="parent",
        foreign_keys="[Folder.parent_id]",
        cascade="all, delete-orphan"
    )

    # Files in this folder
    files = relationship(
        "File",
        back_populates="folder",
        cascade="all, delete-orphan"
    )

    # User relationship
    user = relationship("User", back_populates="folders")

    __table_args__ = (
        Index('idx_folder_user_parent', 'user_id', 'parent_id'),
    )

    def __repr__(self):
        return f"<Folder {self.id} - {self.name}>"


class File(Base):
    """
    User file with storage reference.

    Files are stored on Railway volume at storage_path.
    Metadata includes type categorization, size tracking, and access metrics.
    """

    __tablename__ = "files"

    # Identity
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Containment (null = root level)
    folder_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        index=True,
        nullable=True
    )

    # File info
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_type: Mapped[str] = mapped_column(String(50))  # 'document', 'image', 'code', 'data', 'archive', 'other'
    size_bytes: Mapped[int] = mapped_column(Integer)

    # Storage
    storage_path: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA256

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # Processing state
    status: Mapped[str] = mapped_column(String(20), default="ready")  # 'uploading', 'ready', 'failed'
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Organization
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    # Usage tracking (pattern from AgentMemory)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    user = relationship("User", back_populates="files")
    folder = relationship("Folder", back_populates="files")

    __table_args__ = (
        Index('idx_file_user_folder', 'user_id', 'folder_id'),
        Index('idx_file_user_favorite', 'user_id', 'favorite'),
        Index('idx_file_user_type', 'user_id', 'file_type'),
    )

    def __repr__(self):
        return f"<File {self.id} - {self.name}>"


# ═══════════════════════════════════════════════════════════════════════════════
# FILE TYPE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_EXTENSIONS = {
    # Documents
    'txt', 'md', 'pdf', 'doc', 'docx', 'rtf', 'odt',
    # Code
    'py', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'scss', 'sass', 'less',
    'json', 'yaml', 'yml', 'toml', 'xml', 'sql', 'sh', 'bash', 'zsh',
    'java', 'go', 'rs', 'c', 'cpp', 'h', 'hpp', 'rb', 'php', 'swift', 'kt',
    # Data
    'csv', 'tsv', 'env', 'ini', 'conf', 'log',
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico', 'bmp',
    # Archives
    'zip', 'tar', 'gz', 'tgz',
    # Config
    'gitignore', 'dockerignore', 'editorconfig', 'prettierrc', 'eslintrc',
}

BLOCKED_EXTENSIONS = {
    'exe', 'dll', 'bat', 'cmd', 'msi', 'app', 'dmg', 'iso',
    'com', 'scr', 'pif', 'vbs', 'ps1', 'psm1',
}

FILE_TYPE_MAP = {
    'document': {'txt', 'md', 'pdf', 'doc', 'docx', 'rtf', 'odt'},
    'code': {
        'py', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'scss', 'sass', 'less',
        'json', 'yaml', 'yml', 'toml', 'xml', 'sql', 'sh', 'bash', 'zsh',
        'java', 'go', 'rs', 'c', 'cpp', 'h', 'hpp', 'rb', 'php', 'swift', 'kt',
    },
    'image': {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico', 'bmp'},
    'data': {'csv', 'tsv', 'env', 'ini', 'conf', 'log'},
    'archive': {'zip', 'tar', 'gz', 'tgz'},
}


def get_file_type(extension: str) -> str:
    """Get file type category from extension."""
    ext = extension.lower().lstrip('.')
    for file_type, extensions in FILE_TYPE_MAP.items():
        if ext in extensions:
            return file_type
    return 'other'


def is_allowed_extension(extension: str) -> bool:
    """Check if file extension is allowed."""
    ext = extension.lower().lstrip('.')
    if ext in BLOCKED_EXTENSIONS:
        return False
    return ext in ALLOWED_EXTENSIONS
