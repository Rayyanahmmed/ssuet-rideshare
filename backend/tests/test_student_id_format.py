"""Student ID format (YYYYF-Bcs-NNN) enforced at signup."""

import pytest
from pydantic import ValidationError

from app.models.enums import UserRole
from app.schemas.auth import RegisterIn, normalize_student_id
from tests.helpers import register

BASE = {
    "full_name": "Ali Raza",
    "email": "ali.format@ssuet.edu.pk",
    "password": "Password123",
    "phone": "+923001230001",
    "department": "Computer Science",
    "semester": 5,
    "home_area": "Gulshan-e-Iqbal",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023F-Bcs-301", "2023F-Bcs-301"),
        ("2023f-bcs-301", "2023F-Bcs-301"),
        ("  2023S-Bcs-045 ", "2023S-Bcs-045"),
        ("2024F-Se-120", "2024F-Se-120"),
    ],
)
def test_valid_student_ids_are_normalised(raw, expected):
    assert normalize_student_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "SSUET-2022-101",  # old free-text style
        "2023X-Bcs-301",  # season must be F or S
        "2023F-Bcs-30",  # roll number must be 3 digits
        "2023F-Bcs-3011",
        "23F-Bcs-301",  # year must be 4 digits
        "2023F-B1s-301",  # programme is letters only
        "2023F301",
        "",
    ],
)
def test_invalid_student_ids_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_student_id(raw)


def test_student_registration_schema_enforces_format():
    with pytest.raises(ValidationError):
        RegisterIn(**BASE, role=UserRole.STUDENT, university_id="SSUET-2022-101")


def test_teacher_employee_id_is_not_forced_into_student_format():
    body = RegisterIn(
        full_name="Dr Faheem",
        email="faheem.format@ssuet.edu.pk",
        password="Password123",
        phone="+923001230002",
        role=UserRole.TEACHER,
        university_id="SSUET-EMP-1001",
        department="Computer Science",
        designation="Associate Professor",
    )
    assert body.university_id == "SSUET-EMP-1001"


def test_signup_api_rejects_old_student_id_format(client):
    payload = {
        **BASE,
        "email": "old.format@ssuet.edu.pk",
        "role": "STUDENT",
        "university_id": "SSUET-2022-101",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422, response.text


def test_signup_api_stores_normalised_student_id(client):
    body = register(client, university_id="2023f-bcs-301")
    me = client.get("/api/v1/users/me", headers=body["headers"])
    assert me.status_code == 200, me.text
    assert me.json()["university_id"] == "2023F-Bcs-301"
