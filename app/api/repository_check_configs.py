from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_db, RepositoryCheckConfig
from app.models.schemas import (
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
    RepositoryCheckConfig as RepositoryCheckConfigSchema,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/", response_model=RepositoryCheckConfigSchema)
def create_repository_check_config(
    config: RepositoryCheckConfigCreate, db: Session = Depends(get_db)
):
    """Create a new repository check configuration"""

    # Check if name already exists
    existing = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.name == config.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="A check policy with this name already exists"
        )

    # Create the config
    db_config = RepositoryCheckConfig(
        name=config.name,
        description=config.description,
        check_type=config.check_type,
        verify_data=config.verify_data,
        repair_mode=config.repair_mode,
        save_space=config.save_space,
        max_duration=config.max_duration,
        archive_prefix=config.archive_prefix,
        archive_glob=config.archive_glob,
        first_n_archives=config.first_n_archives,
        last_n_archives=config.last_n_archives,
    )

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    return db_config


@router.get("/", response_model=List[RepositoryCheckConfigSchema])
def get_repository_check_configs(db: Session = Depends(get_db)):
    """Get all repository check configurations"""
    return db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()


@router.get("/form")
async def get_repository_check_form(request: Request, db: Session = Depends(get_db)):
    """Get repository check form with all dropdowns populated"""
    from app.models.database import Repository
    
    repositories = db.query(Repository).all()
    check_configs = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.enabled == True).all()
    
    return templates.TemplateResponse(
        "partials/repository_check/form.html",
        {
            "request": request, 
            "repositories": repositories,
            "check_configs": check_configs
        }
    )


@router.get("/html", response_class=HTMLResponse)
def get_repository_check_configs_html(
    request: Request, db: Session = Depends(get_db)
):
    """Get repository check configurations as HTML"""
    try:
        configs = db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()
        return templates.TemplateResponse(
            "partials/repository_check/config_list_content.html",
            {"request": request, "configs": configs}
        )
    except Exception as e:
        error_html = f'<div class="text-sm text-red-600">Error loading check policies: {str(e)}</div>'
        return HTMLResponse(content=error_html)


@router.get("/{config_id}", response_model=RepositoryCheckConfigSchema)
def get_repository_check_config(config_id: int, db: Session = Depends(get_db)):
    """Get a specific repository check configuration"""
    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    return config


@router.patch("/{config_id}", response_model=RepositoryCheckConfigSchema)
def update_repository_check_config(
    config_id: int,
    update_data: RepositoryCheckConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update a repository check configuration"""

    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")

    # Check for name conflicts if name is being updated
    if update_data.name and update_data.name != config.name:
        existing = (
            db.query(RepositoryCheckConfig)
            .filter(
                RepositoryCheckConfig.name == update_data.name,
                RepositoryCheckConfig.id != config_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="A check policy with this name already exists"
            )

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return config


@router.get("/update-options", response_class=HTMLResponse)
def update_check_options(request: Request, check_type: str = "full", max_duration: str = "", repair_mode: str = ""):
    """Update check options based on check type selection"""
    
    # Determine visibility and state based on check type
    if check_type == "repository_only":
        verify_data_disabled = True
        verify_data_opacity = "0.5"
        time_limit_display = "block"
        archive_filters_display = "none"
    else:
        verify_data_disabled = False
        verify_data_opacity = "1"
        time_limit_display = "none" 
        archive_filters_display = "block"
    
    # Handle repair mode conflict with time limits
    repair_mode_checked = repair_mode and repair_mode.lower() in ['true', 'on', '1']
    repair_mode_disabled = bool(max_duration and max_duration.strip())
    if repair_mode_disabled and repair_mode_checked:
        repair_mode_checked = False
        # Note: We can't show notifications in this context, but the conflict is resolved
    
    options_html = f'''
        <!-- Verification Options -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Options</label>
            <div class="space-y-2">
                <label class="flex items-center" id="verify-data-option" style="opacity: {verify_data_opacity};">
                    <input type="checkbox" name="verify_data" class="mr-2" {'disabled' if verify_data_disabled else ''}>
                    <span class="text-sm">Verify Data Integrity</span>
                    <span class="text-xs text-gray-500 ml-2">(Very slow but thorough)</span>
                </label>
                <label class="flex items-center">
                    <input type="checkbox" name="repair_mode" class="mr-2" id="repair-mode-checkbox" 
                           {'checked' if repair_mode_checked else ''} {'disabled' if repair_mode_disabled else ''}>
                    <span class="text-sm">Repair Mode</span>
                    <span class="text-xs text-red-600 ml-2">⚠️ DANGEROUS - Backup first!</span>
                </label>
                <label class="flex items-center">
                    <input type="checkbox" name="save_space" class="mr-2">
                    <span class="text-sm">Save Space</span>
                    <span class="text-xs text-gray-500 ml-2">(Slower but uses less memory)</span>
                </label>
            </div>
        </div>

        <!-- Advanced Options (Collapsible) -->
        <div>
            <button type="button" onclick="document.getElementById('advanced-options').classList.toggle('hidden'); document.getElementById('advanced-chevron').classList.toggle('rotate-90')" class="flex items-center text-sm text-blue-600 hover:text-blue-800">
                <svg id="advanced-chevron" class="w-4 h-4 mr-1 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                </svg>
                Advanced Options
            </button>
            
            <div id="advanced-options" class="hidden mt-3 p-4 bg-gray-50 rounded-md space-y-4">
                <!-- Time Limit (Repository Only) -->
                <div id="time-limit-section" style="display: {time_limit_display};">
                    <label class="block text-sm font-medium text-gray-700">Time Limit (seconds)</label>
                    <input type="number" name="max_duration" min="1" placeholder="3600" value="{max_duration}"
                           hx-get="/api/repository-check-configs/update-options" 
                           hx-target="#dynamic-check-options" 
                           hx-include="closest form"
                           hx-trigger="change"
                           hx-swap="innerHTML"
                           class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900">
                    <p class="text-xs text-gray-500 mt-1">For partial repository checks only. Leave empty for full check.</p>
                </div>

                <!-- Archive Filters -->
                <div id="archive-filters-section" style="display: {archive_filters_display};">
                    <div class="grid grid-cols-1 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Archive Prefix</label>
                            <input type="text" name="archive_prefix" placeholder="backup-2024" class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700">Archive Glob Pattern</label>
                            <input type="text" name="archive_glob" placeholder="*2024*" class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900">
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700">First N Archives</label>
                                <input type="number" name="first_n_archives" min="1" placeholder="10" class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700">Last N Archives</label>
                                <input type="number" name="last_n_archives" min="1" placeholder="10" class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900">
                            </div>
                        </div>
                    </div>
                    <p class="text-xs text-gray-500 mt-2">Archive filters are only used with Full Check or Archives Only.</p>
                </div>
            </div>
        </div>
    '''
    
    return HTMLResponse(content=options_html)


@router.get("/toggle-custom-options", response_class=HTMLResponse)
def toggle_custom_options(request: Request, check_config_id: str = ""):
    """Toggle custom check options visibility based on policy selection"""
    
    # If a policy is selected (check_config_id has a value), hide custom options
    # If no policy is selected (empty string), show custom options
    show_custom = check_config_id == ""
    
    if show_custom:
        custom_options_html = '''
        <div id="custom-check-options">
            <div class="p-4 bg-gray-50 rounded-md space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Check Type</label>
                    <select name="check_type" class="select-modern w-full">
                        <option value="full">Full Check</option>
                        <option value="repository_only">Repository Only</option>
                        <option value="archives_only">Archives Only</option>
                    </select>
                </div>
                <div class="space-y-2">
                    <label class="flex items-center">
                        <input type="checkbox" name="verify_data" class="mr-2">
                        <span class="text-sm">Verify Data Integrity</span>
                    </label>
                    <label class="flex items-center">
                        <input type="checkbox" name="repair_mode" class="mr-2">
                        <span class="text-sm">Repair Mode ⚠️</span>
                    </label>
                    <label class="flex items-center">
                        <input type="checkbox" name="save_space" class="mr-2">
                        <span class="text-sm">Save Space</span>
                    </label>
                </div>
            </div>
        </div>
        '''
    else:
        custom_options_html = '<div id="custom-check-options" style="display: none;"></div>'
    
    return HTMLResponse(content=custom_options_html)


@router.delete("/{config_id}")
def delete_repository_check_config(config_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a repository check configuration"""

    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")

    # TODO: Check if config is in use by any scheduled backups or jobs
    # For now, we'll allow deletion

    db.delete(config)
    db.commit()

    # Return updated HTML list for HTMX requests
    is_htmx_request = "hx-request" in request.headers
    if is_htmx_request:
        configs = db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()
        return templates.TemplateResponse(
            "partials/repository_check/config_list_content.html",
            {"request": request, "configs": configs}
        )

    return {"message": "Check policy deleted successfully"}
