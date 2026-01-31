"""
Import Endpoints

Import data from local ApexAurum app (conversations, memory).
Supports multiple formats with forgiving parsing.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.auth.deps import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    message: str = ""


def extract_text_content(content) -> str:
    """
    Extract plain text from various content formats.

    Handles:
    - Plain string: "hello" -> "hello"
    - Array of text blocks: [{"type": "text", "text": "hello"}] -> "hello"
    - Array of strings: ["hello", "world"] -> "hello world"
    - Dict with text key: {"text": "hello"} -> "hello"
    - Nested content: {"content": "hello"} -> "hello"
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Handle {"type": "text", "text": "..."} format
                if item.get('type') == 'text' and 'text' in item:
                    parts.append(item['text'])
                # Handle {"text": "..."} format
                elif 'text' in item:
                    parts.append(item['text'])
                # Handle {"content": "..."} format
                elif 'content' in item:
                    parts.append(extract_text_content(item['content']))
        return ' '.join(parts)

    if isinstance(content, dict):
        if 'text' in content:
            return content['text']
        if 'content' in content:
            return extract_text_content(content['content'])

    # Last resort: convert to string
    return str(content)


def parse_timestamp(ts) -> datetime:
    """Parse various timestamp formats into datetime."""
    if ts is None:
        return datetime.utcnow()

    if isinstance(ts, datetime):
        return ts

    if isinstance(ts, (int, float)):
        # Unix timestamp
        try:
            return datetime.fromtimestamp(ts)
        except:
            return datetime.utcnow()

    if isinstance(ts, str):
        # Try various ISO formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]

        # Clean up the string
        ts_clean = ts.replace('Z', '+00:00')

        # Try fromisoformat first (handles most cases)
        try:
            return datetime.fromisoformat(ts_clean)
        except:
            pass

        # Try each format
        for fmt in formats:
            try:
                return datetime.strptime(ts.split('+')[0].split('Z')[0], fmt)
            except:
                continue

    return datetime.utcnow()


def generate_title(messages: list, max_length: int = 50) -> str:
    """Generate a title from the first user message."""
    for msg in messages:
        if msg.get('role') == 'user':
            content = extract_text_content(msg.get('content', ''))
            if content:
                # Truncate and clean
                title = content[:max_length].strip()
                if len(content) > max_length:
                    title += '...'
                return title
    return 'Imported Conversation'


@router.post("/conversations", response_model=ImportResult)
async def import_conversations(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Import conversations from local ApexAurum app.

    Supports multiple formats:

    1. Array format (Streamlit/local app):
    [
      {
        "id": "conv_xxx",
        "created_at": "...",
        "messages": [{"role": "user", "content": [...]}]
      }
    ]

    2. Dict format (keyed by ID):
    {
      "conv_id": {"title": "...", "messages": [...]}
    }

    3. Cloud export format:
    [
      {"title": "...", "created_at": "...", "messages": [...]}
    ]

    Messages can have content as:
    - Plain string: "hello"
    - Array of text blocks: [{"type": "text", "text": "hello"}]
    """
    # Check authentication
    if not user:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=["Authentication required. Please log in and try again."],
            message="Please log in to import conversations."
        )

    # Parse JSON
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
    except json.JSONDecodeError as e:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=[f"Invalid JSON: {str(e)}"],
            message="Could not parse JSON file."
        )
    except UnicodeDecodeError as e:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=[f"Encoding error: {str(e)}"],
            message="Could not decode file. Please ensure it's UTF-8 encoded."
        )

    # Normalize to list of conversations
    conversations = []
    if isinstance(data, list):
        conversations = data
    elif isinstance(data, dict):
        # Could be keyed by ID or a single conversation
        if 'messages' in data:
            # Single conversation
            conversations = [data]
        else:
            # Dict keyed by IDs
            conversations = list(data.values())
    else:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=["Invalid format. Expected array or object."],
            message="Unrecognized file format."
        )

    imported = 0
    skipped = 0
    errors = []

    for i, conv_data in enumerate(conversations):
        try:
            if not isinstance(conv_data, dict):
                errors.append(f"Item {i}: Not a valid conversation object")
                skipped += 1
                continue

            messages_data = conv_data.get('messages', [])
            if not messages_data:
                errors.append(f"Item {i}: No messages found")
                skipped += 1
                continue

            # Parse timestamps
            created_at = parse_timestamp(conv_data.get('created_at'))
            updated_at = parse_timestamp(conv_data.get('updated_at', conv_data.get('created_at')))

            # Get or generate title
            title = conv_data.get('title') or generate_title(messages_data)

            # Create conversation
            conv = Conversation(
                id=uuid4(),
                user_id=user.id,
                title=title[:200],
                created_at=created_at,
                updated_at=updated_at,
                favorite=conv_data.get('favorite', False),
                tags=conv_data.get('tags', []) if isinstance(conv_data.get('tags'), list) else [],
            )
            db.add(conv)
            await db.flush()

            # Import messages
            msg_count = 0
            for msg_data in messages_data:
                if not isinstance(msg_data, dict):
                    continue

                content = extract_text_content(msg_data.get('content', ''))
                if not content.strip():
                    continue

                role = msg_data.get('role', 'user')
                if role not in ('user', 'assistant', 'system'):
                    role = 'user'

                msg_time = parse_timestamp(
                    msg_data.get('timestamp') or
                    msg_data.get('created_at') or
                    msg_data.get('time')
                )

                message = Message(
                    id=uuid4(),
                    conversation_id=conv.id,
                    role=role,
                    content=content,
                    created_at=msg_time,
                )
                db.add(message)
                msg_count += 1

            if msg_count > 0:
                imported += 1
            else:
                # No valid messages, remove the conversation
                await db.delete(conv)
                errors.append(f"Item {i}: No valid messages")
                skipped += 1

        except Exception as e:
            logger.warning(f"Failed to import conversation {i}: {e}")
            errors.append(f"Item {i}: {str(e)[:100]}")
            skipped += 1

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Database commit failed: {e}")
        return ImportResult(
            imported=0,
            skipped=len(conversations),
            errors=[f"Database error: {str(e)}"],
            message="Failed to save to database."
        )

    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors[:20],
        message=f"Successfully imported {imported} conversations."
    )


@router.post("/memory", response_model=ImportResult)
async def import_memory(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Import memory from local ApexAurum app.

    Accepts the sandbox/memory.json format:
    {
      "key_name": {
        "value": any,
        "stored_at": "ISO_8601",
        "metadata": {}
      }
    }

    Memory is stored in the user's settings JSON field.
    """
    # Check authentication
    if not user:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=["Authentication required. Please log in and try again."],
            message="Please log in to import memory."
        )

    # Parse JSON
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
    except json.JSONDecodeError as e:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=[f"Invalid JSON: {str(e)}"],
            message="Could not parse JSON file."
        )
    except UnicodeDecodeError as e:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=[f"Encoding error: {str(e)}"],
            message="Could not decode file. Please ensure it's UTF-8 encoded."
        )

    if not isinstance(data, dict):
        return ImportResult(
            imported=0,
            skipped=0,
            errors=["Invalid format. Expected object with key-value entries."],
            message="Unrecognized file format."
        )

    # Initialize user settings if needed
    if not user.settings:
        user.settings = {}

    if 'imported_memory' not in user.settings:
        user.settings['imported_memory'] = {}

    imported = 0
    skipped = 0
    errors = []

    for key, entry in data.items():
        try:
            # Handle various entry formats
            if isinstance(entry, dict):
                value = entry.get('value', entry)
                stored_at = entry.get('stored_at', datetime.utcnow().isoformat())
                metadata = entry.get('metadata', {})
            else:
                # Direct value without wrapper
                value = entry
                stored_at = datetime.utcnow().isoformat()
                metadata = {}

            user.settings['imported_memory'][key] = {
                'value': value,
                'stored_at': stored_at,
                'metadata': metadata if isinstance(metadata, dict) else {},
                'imported_at': datetime.utcnow().isoformat(),
            }
            imported += 1
        except Exception as e:
            logger.warning(f"Failed to import memory key {key}: {e}")
            errors.append(f"Key '{key[:50]}': {str(e)[:50]}")
            skipped += 1

    try:
        # Mark settings as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, 'settings')
        await db.commit()
    except Exception as e:
        logger.error(f"Database commit failed: {e}")
        return ImportResult(
            imported=0,
            skipped=len(data),
            errors=[f"Database error: {str(e)}"],
            message="Failed to save to database."
        )

    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors[:20],
        message=f"Successfully imported {imported} memory entries."
    )


@router.get("/memory")
async def get_imported_memory(
    user: User = Depends(get_current_user_optional),
):
    """Get user's imported memory."""
    if not user or not user.settings:
        return {"memory": {}, "count": 0}

    memory = user.settings.get('imported_memory', {})
    return {"memory": memory, "count": len(memory)}
