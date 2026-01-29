from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# =========================
# Perfil y preferencias
# =========================

class Preferences(BaseModel):
    weight_match: float = Field(..., ge=0, le=1)
    weight_prestige: float = Field(..., ge=0, le=1)
    weight_cost: float = Field(..., ge=0, le=1)


class MyProfile(BaseModel):
    name: Optional[str] = None
    country: str
    currency: str
    preferences: Preferences


# =========================
# Estudios actuales
# =========================

class Course(BaseModel):
    name: str
    credits: Optional[float] = None


class CurrentStudies(BaseModel):
    degree: str
    current_university: Optional[str] = None  # 👈 YA NO OBLIGATORIO
    curriculum_file: Optional[str] = None
    courses: Optional[List[Course]] = None


# =========================
# Targets
# =========================

class UniversityTarget(BaseModel):
    name: str
    city: str
    program_query: Optional[str] = None
    program_urls: Optional[List[str]] = None


class Targets(BaseModel):
    universities: List[UniversityTarget]


# =========================
# Mission principal
# =========================

class Mission(BaseModel):
    id: str
    goal: str
    my_profile: MyProfile
    current_studies: CurrentStudies
    targets: Targets


# =========================
# Resultados
# =========================

class ResultRow(BaseModel):
    university: str
    city: str
    match_pct: float
    prestige_score: float
    cost_score: float
    final_score: float
    notes: Optional[str] = None
