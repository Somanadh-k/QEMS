from pydantic import BaseModel, ConfigDict


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: int
    name: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    name: str
    sla_policy_id: int | None


class UserOut(BaseModel):
    user_id: int
    full_name: str
    department_id: int | None
    roles: list[str]
