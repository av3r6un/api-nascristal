from pydantic import BaseModel, Field

from src.models.user import Role


class RegisterRequest(BaseModel):
  email: str
  password: str = Field(min_length=8, max_length=128)
  role: Role = Role.MANAGER


class LoginRequest(BaseModel):
  email: str
  password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
  refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
  uid: str
  email: str
  role: Role


class TokensResponse(BaseModel):
  accs_token: str
  rfsh_token: str | None = None


class AuthResponse(BaseModel):
  user: UserResponse
  tokens: TokensResponse


class RefreshResponse(BaseModel):
  accs_token: str
