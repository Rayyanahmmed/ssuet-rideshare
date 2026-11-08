"""ORM model registry.

Importing this module registers every table on `Base.metadata`, which is what
Alembic autogenerate and the seed script rely on.
"""

from app.db.base import Base
from app.models.admin_action import AdminAction
from app.models.app_setting import AppSetting
from app.models.chat import Conversation, Message
from app.models.enums import (
    AccountStatus,
    AdminActionType,
    ContributionType,
    FuelPreference,
    NotificationType,
    ReportCategory,
    ReportStatus,
    RideDirection,
    RideRequestStatus,
    RideStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
    VehicleType,
    VerificationStatus,
    VerificationType,
)
from app.models.media import MediaAsset
from app.models.notification import DeviceToken, Notification
from app.models.report import Report
from app.models.review import Review
from app.models.ride import Ride, RideRequest
from app.models.trip import Trip
from app.models.user import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    StudentProfile,
    TeacherProfile,
    User,
    UserBlock,
)
from app.models.vehicle import Vehicle
from app.models.verification import Verification

__all__ = [
    "Base",
    "User", "StudentProfile", "TeacherProfile", "RefreshToken", "PasswordResetToken",
    "EmailVerificationToken", "UserBlock",
    "Vehicle",
    "Ride", "RideRequest",
    "Trip",
    "Conversation", "Message",
    "Notification", "DeviceToken",
    "MediaAsset",
    "Review",
    "Report",
    "Verification",
    "AdminAction",
    # enums
    "UserRole", "AccountStatus", "VerificationStatus", "VerificationType",
    "VehicleType", "VehicleStatus", "RideDirection", "FuelPreference",
    "ContributionType", "RideStatus", "RideRequestStatus", "TripStatus",
    "NotificationType", "ReportCategory", "ReportStatus", "AdminActionType",
    "AppSetting",
]
