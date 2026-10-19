"""Register a browser folder handle. Implements: REQ-004, REQ-012."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, require_user
from app.db.models import LocalWorkspaceMount
from app.db.session import database_session
from app.tool_bus.audit import record_security_audit
from app.tool_bus.local_path_policy import local_path_violation

router = APIRouter()


class MountFile(BaseModel):
    path: str
    size: int = 0
    lastModified: int = 0


class MountRegister(BaseModel):
    mount_alias: str = Field(min_length=1, max_length=100)
    browser_handle_key: str = Field(min_length=1, max_length=255)
    file_tree: list[MountFile] = Field(default_factory=list)


@router.post("/mounts/register", status_code=201)
async def register_mount(body: MountRegister, user: CurrentUser = Depends(require_user)) -> dict[str, str]:
    for entry in body.file_tree:
        violation = local_path_violation(entry.path)
        if violation is None:
            continue
        await record_security_audit(
            actor_user_id=str(user.id),
            event_code=violation,
            resource=entry.path,
            detail="掛載檔案樹包含敏感或越權路徑",
        )
        raise HTTPException(status_code=400, detail=f"Security Violation: 禁止掛載敏感或越權路徑 ({entry.path})")
    async with database_session() as db:
        mount = LocalWorkspaceMount(
            user_id=user.id,
            mount_alias=body.mount_alias,
            provider_type="BROWSER_FS_API",
            browser_handle_key=body.browser_handle_key,
            permission_mode="READ_WRITE_WITH_CONFIRM",
            cached_file_tree=[entry.model_dump() for entry in body.file_tree],
        )
        db.add(mount)
        await db.flush()
        await db.refresh(mount)
        mount_id = str(mount.id)
    return {
        "id": mount_id,
        "mount_alias": body.mount_alias,
        "browser_handle_key": body.browser_handle_key,
    }
