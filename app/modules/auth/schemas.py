# app/modules/auth/schemas.py
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ USER ============
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=100)
    full_name: str
    email: str = ""
    phone: str = ""
    role_ids: List[int] = []
    note: str = ""


class UserUpdate(BaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
    status: str = "ACTIVE"
    role_ids: List[int] = []
    note: str = ""


class UserChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4, max_length=100)


class AdminResetPassword(BaseModel):
    new_password: str = Field(min_length=4, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False


# ============ ROLE ============
class RoleCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    permission_ids: List[int] = []


class RoleUpdate(BaseModel):
    name: str
    description: str = ""
    permission_ids: List[int] = []


# ============ PROFILE ============
class ProfileUpdate(BaseModel):
    full_name: str
    email: str = ""
    phone: str = ""
