from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_db, RepositoryCheckConfig
from app.models.schemas import RepositoryCheckConfigCreate, RepositoryCheckConfigUpdate, RepositoryCheckConfig as RepositoryCheckConfigSchema

router = APIRouter()


@router.post("/", response_model=RepositoryCheckConfigSchema)
def create_repository_check_config(
    config: RepositoryCheckConfigCreate,
    db: Session = Depends(get_db)
):
    """Create a new repository check configuration"""
    
    # Check if name already exists
    existing = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.name == config.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A check policy with this name already exists")
    
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
        last_n_archives=config.last_n_archives
    )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    return db_config


@router.get("/", response_model=List[RepositoryCheckConfigSchema])
def get_repository_check_configs(db: Session = Depends(get_db)):
    """Get all repository check configurations"""
    return db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()


@router.get("/{config_id}", response_model=RepositoryCheckConfigSchema)
def get_repository_check_config(config_id: int, db: Session = Depends(get_db)):
    """Get a specific repository check configuration"""
    config = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    return config


@router.patch("/{config_id}", response_model=RepositoryCheckConfigSchema)
def update_repository_check_config(
    config_id: int,
    update_data: RepositoryCheckConfigUpdate,
    db: Session = Depends(get_db)
):
    """Update a repository check configuration"""
    
    config = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    
    # Check for name conflicts if name is being updated
    if update_data.name and update_data.name != config.name:
        existing = db.query(RepositoryCheckConfig).filter(
            RepositoryCheckConfig.name == update_data.name,
            RepositoryCheckConfig.id != config_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="A check policy with this name already exists")
    
    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(config, field, value)
    
    db.commit()
    db.refresh(config)
    
    return config


@router.delete("/{config_id}")
def delete_repository_check_config(config_id: int, db: Session = Depends(get_db)):
    """Delete a repository check configuration"""
    
    config = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    
    # TODO: Check if config is in use by any scheduled backups or jobs
    # For now, we'll allow deletion
    
    db.delete(config)
    db.commit()
    
    return {"message": "Check policy deleted successfully"}