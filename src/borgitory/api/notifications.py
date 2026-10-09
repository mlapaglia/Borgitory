"""
API endpoints for managing Apprise notification configurations.
"""

import logging
import re
import html
from dataclasses import dataclass
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData
from starlette.templating import _TemplateResponse

from borgitory.dependencies import (
    AppriseCatalogDep,
    NotificationConfigServiceDep,
    TemplatesDep,
    get_browser_timezone_offset,
    get_db,
    get_notification_service,
)
from borgitory.models.database import NotificationConfig, User
from borgitory.services.notifications.apprise_storage import (
    MANUAL_SERVICE_ID,
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.service import (
    NotificationEditView,
    NotificationService,
)
from borgitory.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_FIELD_NAME_RE = re.compile(r"^fields\[([\w-]+)\]$")


@dataclass
class NotificationConfigSummary:
    """Display details for a configured notification"""

    config: NotificationConfig
    service_name: str
    needs_attention: Optional[str] = None


def _form_str(form_data: FormData, key: str) -> str:
    value = form_data.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _parse_submission(form_data: FormData) -> AppriseSubmission:
    """Read the service selection and its field values from a submitted form"""
    service = _form_str(form_data, "service")
    if service == MANUAL_SERVICE_ID:
        urls = form_data.get("urls", "")
        return AppriseSubmission(
            mode="manual", urls=urls if isinstance(urls, str) else ""
        )

    values: Dict[str, str] = {}
    for key, value in form_data.multi_items():
        match = _FIELD_NAME_RE.match(key)
        if match and isinstance(value, str):
            values[match.group(1)] = value
    return AppriseSubmission(mode="service", service=service or None, values=values)


def _parse_config_id(form_data: FormData) -> Optional[int]:
    raw = _form_str(form_data, "config_id")
    return int(raw) if raw.isdigit() else None


def _summarize_config(config: NotificationConfig) -> NotificationConfigSummary:
    stored = StoredAppriseConfig.try_decode(config.provider_config)
    if config.provider != "apprise" or stored is None:
        return NotificationConfigSummary(
            config=config,
            service_name=config.provider.title(),
            needs_attention="Unsupported format - edit and save to re-configure",
        )
    return NotificationConfigSummary(
        config=config,
        service_name=stored.service_name,
        needs_attention=stored.migration_error,
    )


@router.get("/service-fields", response_class=HTMLResponse)
async def get_service_fields(
    request: Request,
    templates: TemplatesDep,
    catalog: AppriseCatalogDep,
    config_service: NotificationConfigServiceDep,
    service: Optional[str] = None,
    config_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Get the form fields for an Apprise service"""
    if not service:
        return HTMLResponse("")

    edit_view: Optional[NotificationEditView] = None
    if config_id is not None:
        _, edit_view = await config_service.get_config_for_edit(db, config_id)

    if service == MANUAL_SERVICE_ID:
        masked_urls: List[str] = []
        if edit_view is not None and edit_view.mode == "manual":
            masked_urls = edit_view.masked_urls
        return templates.TemplateResponse(
            request,
            "partials/notifications/manual_fields.html",
            {"is_edit": config_id is not None, "masked_urls": masked_urls},
        )

    apprise_service = catalog.get(service)
    if apprise_service is None:
        return HTMLResponse(
            f'<div class="text-red-500">Unknown notification service: {html.escape(service)}</div>'
        )

    field_values: Dict[str, str] = {}
    stored_private_keys: frozenset[str] = frozenset()
    if (
        edit_view is not None
        and edit_view.service is not None
        and edit_view.service.id == apprise_service.id
    ):
        field_values = edit_view.field_values
        stored_private_keys = edit_view.stored_private_keys

    return templates.TemplateResponse(
        request,
        "partials/notifications/apprise_fields.html",
        {
            "service": apprise_service,
            "field_values": field_values,
            "stored_private_keys": stored_private_keys,
            "is_edit": config_id is not None,
        },
    )


@router.post("/", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_config(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Create a new notification configuration"""
    try:
        form_data = await request.form()
        name = _form_str(form_data, "name")
        submission = _parse_submission(form_data)

        if not name or (submission.mode == "service" and not submission.service):
            return templates.TemplateResponse(
                request,
                "partials/notifications/create_error.html",
                {"error_message": "Name and notification service are required"},
                status_code=400,
            )

        try:
            db_config = await config_service.create_config(
                db=db, name=name, submission=submission
            )
        except HTTPException as e:
            return templates.TemplateResponse(
                request,
                "partials/notifications/create_error.html",
                {"error_message": e.detail},
                status_code=e.status_code,
            )

        response = templates.TemplateResponse(
            request,
            "partials/notifications/create_success.html",
            {"config_name": db_config.name},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except Exception as e:
        logger.error(f"Error creating notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/create_error.html",
            {"error_message": f"Failed to create notification: {str(e)}"},
            status_code=500,
        )


@router.get("/html", response_class=HTMLResponse)
async def get_notification_configs_html(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Get notification configurations as formatted HTML"""
    try:
        configs = await config_service.get_all_configs(db)
        summaries = [_summarize_config(config) for config in configs]

        browser_tz_offset = get_browser_timezone_offset(request)
        return HTMLResponse(
            templates.get_template(
                "partials/notifications/config_list_content.html"
            ).render(
                request=request,
                summaries=summaries,
                browser_tz_offset=browser_tz_offset,
            )
        )

    except Exception as e:
        return HTMLResponse(
            templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading notification configurations: {str(e)}",
                padding="4",
            )
        )


@router.post("/test", response_class=HTMLResponse)
async def test_notification_submission(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Send a test notification using unsaved form values"""
    try:
        form_data = await request.form()
        submission = _parse_submission(form_data)
        if submission.mode == "service" and not submission.service:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": "Select a notification service first"},
                status_code=400,
            )

        success, message = await config_service.test_submission(
            db, submission, _parse_config_id(form_data)
        )
        if success:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_success.html",
                {"message": message},
            )
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": message},
            status_code=400,
        )

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        logger.error(f"Error testing notification settings: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": f"Test failed: {str(e)}"},
            status_code=500,
        )


@router.post("/{config_id}/test", response_class=HTMLResponse)
async def test_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    notification_service: NotificationService = Depends(get_notification_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Send a test notification for a saved configuration"""
    try:
        success, message = await config_service.test_config_with_service(
            db, config_id, notification_service
        )

        if success:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_success.html",
                {"message": message},
            )
        else:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": message},
                status_code=400,
            )

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        logger.error(f"Error testing notification config {config_id}: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": f"Test failed: {str(e)}"},
            status_code=500,
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Enable a notification configuration"""
    try:
        success, message = await config_service.enable_config(db, config_id)

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to enable notification: {str(e)}"},
            status_code=500,
        )


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Disable a notification configuration"""
    try:
        success, message = await config_service.disable_config(db, config_id)

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to disable notification: {str(e)}"},
            status_code=500,
        )


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_notification_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    catalog: AppriseCatalogDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Get edit form for a specific notification configuration"""
    try:
        config, edit_view = await config_service.get_config_for_edit(db, config_id)

        if edit_view.service is not None:
            selected_service = edit_view.service.id
        elif edit_view.mode == "manual":
            selected_service = MANUAL_SERVICE_ID
        else:
            selected_service = ""

        return templates.TemplateResponse(
            request,
            "partials/notifications/edit_form.html",
            {
                "config": config,
                "edit_view": edit_view,
                "service_groups": catalog.grouped(),
                "selected_service": selected_service,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error loading edit form: {str(e)}"
        )


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Update a notification configuration"""
    try:
        form_data = await request.form()
        name = _form_str(form_data, "name")
        submission = _parse_submission(form_data)

        if not name or (submission.mode == "service" and not submission.service):
            return templates.TemplateResponse(
                request,
                "partials/notifications/update_error.html",
                {"error_message": "Name and notification service are required"},
                status_code=400,
            )

        try:
            updated_config = await config_service.update_config(
                db=db, config_id=config_id, name=name, submission=submission
            )
        except HTTPException as e:
            return templates.TemplateResponse(
                request,
                "partials/notifications/update_error.html",
                {"error_message": e.detail},
                status_code=e.status_code,
            )

        response = templates.TemplateResponse(
            request,
            "partials/notifications/update_success.html",
            {"config_name": updated_config.name},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except Exception as e:
        logger.error(f"Error updating notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/update_error.html",
            {"error_message": f"Failed to update notification: {str(e)}"},
            status_code=500,
        )


@router.get("/form", response_class=HTMLResponse)
async def get_notification_form(
    request: Request,
    templates: TemplatesDep,
    catalog: AppriseCatalogDep,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Get notification creation form"""
    try:
        return templates.TemplateResponse(
            request,
            "partials/notifications/add_form.html",
            {"service_groups": catalog.grouped()},
        )
    except Exception as e:
        logger.error(f"Error getting notification form: {e}")
        return HTMLResponse(
            '<div class="text-red-500">Failed to load notification form.</div>',
            status_code=500,
        )


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _TemplateResponse:
    """Delete a notification configuration"""
    try:
        success, config_name = await config_service.delete_config(db, config_id)

        message = f"Notification configuration '{config_name}' deleted successfully!"

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        logger.error(f"Error deleting notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to delete notification: {str(e)}"},
            status_code=500,
        )
