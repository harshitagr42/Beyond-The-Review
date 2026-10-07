from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.repositories.base import Repository
from app.services.analytics_service import AnalyticsService
from app.services.governance_service import GovernanceService
from app.services.job_service import JobService
from app.services.theme_service import ThemeService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_jobs(request: Request) -> JobService:
    return request.app.state.jobs


def get_analytics(request: Request) -> AnalyticsService:
    return request.app.state.analytics


def get_themes(request: Request) -> ThemeService:
    return request.app.state.themes


def get_governance(request: Request) -> GovernanceService:
    return request.app.state.governance
