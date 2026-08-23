from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class Employee(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str
    name: str
    email: EmailStr
    date_of_birth: Optional[str] = None
    department: Optional[str] = None
    joining_date: Optional[str] = None

TARGET_SCHEMA = {
    "employee_id": {"type": "string", "required": True, "description": "Unique employee identifier"},
    "name": {"type": "string", "required": True, "description": "Employee full name"},
    "email": {"type": "email", "required": True, "description": "Employee email address"},
    "date_of_birth": {"type": "date", "required": False, "description": "Employee date of birth, ISO YYYY-MM-DD"},
    "department": {"type": "string", "required": False, "description": "Employee department"},
    "joining_date": {"type": "date", "required": False, "description": "Employee joining date, ISO YYYY-MM-DD"},
}
