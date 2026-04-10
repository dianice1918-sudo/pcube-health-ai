from pydantic import BaseModel, EmailStr, Field
from datetime import date, datetime
from typing import Any, Dict, Optional, List

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    tenant_name: Optional[str] = None


class UserLocationPermissionUpdate(BaseModel):
    granted: bool


class UserLocationUpdate(BaseModel):
    latitude: float
    longitude: float
    label: Optional[str] = None


class UserLocationOut(BaseModel):
    location_permission_granted: bool
    location_updated_at: Optional[datetime] = None
    region_monitoring_enabled: bool = False
    status_message: Optional[str] = None


class StepSyncRequest(BaseModel):
    device_id: str = Field(default="android-primary", min_length=1, max_length=120)
    sensor_type: str = Field(default="STEP_COUNTER", description="STEP_COUNTER | STEP_DETECTOR | ACCELEROMETER")
    timezone: Optional[str] = Field(default=None, max_length=64)
    event_time: Optional[datetime] = None
    record_date: Optional[date] = None
    boot_id: Optional[str] = Field(default=None, max_length=120)
    total_steps_since_boot: Optional[int] = Field(default=None, ge=0)
    detected_steps_delta: Optional[int] = Field(default=None, ge=0)
    step_delta: Optional[int] = Field(default=None, ge=0)
    activity_minutes_delta: int = 0
    algorithm_version: Optional[str] = Field(default=None, max_length=60)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class StepSyncResponse(BaseModel):
    user_id: int
    tenant_id: int
    device_id: str
    sensor_type: str
    processing_mode: str
    record_date: date
    accepted_step_delta: int
    daily_steps_from_sensor: int
    total_steps: int
    total_activity_minutes: int
    warning: Optional[str] = None


class PushTokenRegister(BaseModel):
    provider: str = "fcm"
    platform: str
    device_label: Optional[str] = None
    push_token: str


class PushTokenOut(BaseModel):
    id: int
    provider: str
    platform: str
    device_label: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_seen_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WearableConnectRequest(BaseModel):
    provider: str
    external_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class WearableConnectionOut(BaseModel):
    id: int
    provider: str
    external_user_id: Optional[str] = None
    scope: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WearableSyncRequest(BaseModel):
    provider: str
    record_date: Optional[date] = None
    steps_count: Optional[int] = Field(default=None, ge=0)
    activity_minutes: Optional[int] = Field(default=None, ge=0)
    hydration_liters: Optional[float] = Field(default=None, ge=0)
    resting_heart_rate: Optional[float] = Field(default=None, ge=0)
    source_payload: Optional[Dict[str, Any]] = None


class WearableSyncResponse(BaseModel):
    user_id: int
    tenant_id: int
    provider: str
    record_id: int
    record_date: date
    synced_fields: List[str] = Field(default_factory=list)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginCodeChallengeOut(BaseModel):
    challenge_id: str
    otp_required: bool = True
    delivery_channel: str = "email"
    destination_masked: str
    expires_at: datetime
    expires_in_seconds: int
    message: str
    debug_code: str | None = None


class LoginCodeVerifyIn(BaseModel):
    challenge_id: str
    code: str = Field(min_length=4, max_length=12)


class HealthRecordCreate(BaseModel):
    record_date: date
    systolic_bp: float
    diastolic_bp: float
    bmi: float
    blood_glucose: float
    cholesterol: float
    smoking_status: str
    activity_level: str
    steps_count: Optional[int] = None
    activity_minutes: Optional[int] = None
    resting_heart_rate: Optional[float] = None
    hydration_liters: Optional[float] = None
    city: Optional[str] = None
    weather_condition: Optional[str] = None
    temperature_c: Optional[float] = None
    uv_index: Optional[float] = None
    aqi: Optional[int] = None


class HealthRecordOut(BaseModel):
    id: int
    user_id: int
    tenant_id: Optional[int] = None
    record_date: date
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    bmi: Optional[float] = None
    blood_glucose: Optional[float] = None
    cholesterol: Optional[float] = None
    smoking_status: str
    activity_level: str
    steps_count: Optional[int] = None
    activity_minutes: Optional[int] = None
    resting_heart_rate: Optional[float] = None
    hydration_liters: Optional[float] = None
    city: Optional[str] = None
    weather_condition: Optional[str] = None
    temperature_c: Optional[float] = None
    uv_index: Optional[float] = None
    aqi: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True 


class RiskHistoryOut(BaseModel):
    id: int
    user_id: int
    tenant_id: Optional[int] = None
    risk_score: float
    risk_level: str
    trend: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class HealthIngestResponse(BaseModel):
    record: HealthRecordOut
    current_risk: Optional[float] = None
    risk_level: Optional[str] = None
    trend: str
    next_risk_prediction: Optional[float] = None
    alert_triggered: bool = False
    alert_suppressed_due_to_plan: bool = False
    hydration_alert: Optional[str] = None
    activity_tip: Optional[str] = None
    environment_tips: List[str] = Field(default_factory=list)
    outbreak_alerts: List[str] = Field(default_factory=list)


class TrendOut(BaseModel):
    trend: str
    sample_size: int


class ForecastOut(BaseModel):
    next_risk_prediction: Optional[float] = None
    based_on_points: int


class AdminUserRiskOut(BaseModel):
    user_id: int
    email: Optional[str] = None
    full_name: Optional[str] = None
    latest_risk_score: float
    latest_risk_level: str
    recorded_at: datetime


class AdminSystemStatsOut(BaseModel):
    total_users: int
    total_health_records: int
    total_risk_history_entries: int
    high_risk_users: int


class TenantCreate(BaseModel):
    name: str


class TenantOut(BaseModel):
    id: int
    name: str
    subscription_tier: str
    daily_record_limit: int
    monthly_alert_limit: int
    monthly_chat_limit: int
    monthly_image_chat_limit: int
    created_at: datetime

    class Config:
        from_attributes = True


class TenantPlanUpdate(BaseModel):
    subscription_tier: str


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreated(BaseModel):
    id: int
    tenant_id: int
    name: str
    key_prefix: str
    api_key: str
    created_at: datetime


class WebhookCreate(BaseModel):
    url: str
    events: Optional[List[str]] = None


class WebhookOut(BaseModel):
    id: int
    tenant_id: int
    url: str
    events: List[str]
    is_active: bool
    created_at: datetime


class WebhookSecretRotateOut(BaseModel):
    id: int
    signing_secret: str


class ChatAskRequest(BaseModel):
    question: str


class ChatLoopRequest(BaseModel):
    message: str


class ChatLoopResponse(BaseModel):
    response: str
    llm_model: Optional[str] = None
    remaining: Optional[int] = None


class ChatAskImageRequest(BaseModel):
    question: str
    image_base64: str
    image_mime_type: str = "image/jpeg"


class ChatAskResponse(BaseModel):
    answer: str
    llm_model: Optional[str] = None
    plan_tier: str
    used_this_month: int
    monthly_limit: int
    remaining: int
    image_used: bool = False
    image_used_this_month: int = 0
    image_monthly_limit: int = 0
    image_remaining: int = 0


class AssistantFileOut(BaseModel):
    id: Optional[str] = None
    name: str
    status: Optional[str] = None
    percent_done: Optional[float] = None
    error_message: Optional[str] = None
    created_on: Optional[str] = None
    updated_on: Optional[str] = None


class AssistantFilesResponse(BaseModel):
    provider: str
    assistant_name: Optional[str] = None
    upload_enabled: bool = False
    status_message: Optional[str] = None
    supported_types: List[str] = Field(default_factory=list)
    files: List[AssistantFileOut] = Field(default_factory=list)


class AssistantFileUploadResponse(BaseModel):
    provider: str
    assistant_name: str
    message: str
    file: AssistantFileOut


class MedicationPlanRequest(BaseModel):
    primary_complaint: str = Field(min_length=2, max_length=400)
    age_range: Optional[str] = Field(default=None, max_length=40)
    risk_level: Optional[str] = Field(default=None, max_length=40)
    allergies: Optional[str] = Field(default=None, max_length=400)
    current_medications: Optional[str] = Field(default=None, max_length=600)
    additional_notes: Optional[str] = Field(default=None, max_length=1200)


class MedicationPlanResponse(BaseModel):
    answer: str
    llm_model: Optional[str] = None
    plan_tier: str
    used_this_month: int
    monthly_limit: int
    remaining: int


class NutritionLogCreate(BaseModel):
    entry_date: Optional[date] = None
    meal_type: Optional[str] = Field(default=None, max_length=40)
    calories: Optional[int] = Field(default=None, ge=0, le=8000)
    water_liters: Optional[float] = Field(default=None, ge=0, le=12)
    symptoms: Optional[str] = Field(default=None, max_length=600)
    goals: Optional[str] = Field(default=None, max_length=400)
    notes: Optional[str] = Field(default=None, max_length=1200)


class NutritionLogOut(BaseModel):
    id: int
    entry_date: date
    meal_type: Optional[str] = None
    calories: Optional[int] = None
    water_liters: Optional[float] = None
    symptoms: Optional[str] = None
    goals: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NutritionSummaryOut(BaseModel):
    plan_tier: str
    calorie_goal: int
    water_goal_liters: float
    today_calories: int = 0
    today_water_liters: float = 0
    avg_daily_calories_7d: Optional[int] = None
    avg_daily_water_liters_7d: Optional[float] = None
    health_context: List[str] = Field(default_factory=list)
    recent_logs: List[NutritionLogOut] = Field(default_factory=list)
    pro_unlock_message: str


class NutritionPlanRequest(BaseModel):
    goal: str = Field(min_length=2, max_length=240)
    symptom_focus: Optional[str] = Field(default=None, max_length=500)
    dietary_preferences: Optional[str] = Field(default=None, max_length=400)
    allergies: Optional[str] = Field(default=None, max_length=400)
    budget_level: Optional[str] = Field(default=None, max_length=40)
    cooking_time: Optional[str] = Field(default=None, max_length=80)
    additional_notes: Optional[str] = Field(default=None, max_length=1200)


class NutritionPlanResponse(BaseModel):
    answer: str
    llm_model: Optional[str] = None
    plan_tier: str
    used_this_month: int
    monthly_limit: int
    remaining: int


class PeerInsightItem(BaseModel):
    title: str
    detail: str
    evidence: Optional[str] = None


class CommunityInsightsResponse(BaseModel):
    plan_tier: str
    cohort_size: int
    overview: str
    matched_topics: List[str] = Field(default_factory=list)
    habit_trends: List[PeerInsightItem] = Field(default_factory=list)
    symptom_patterns: List[PeerInsightItem] = Field(default_factory=list)
    nutrition_patterns: List[PeerInsightItem] = Field(default_factory=list)
    privacy_note: str


class ChatMessageOut(BaseModel):
    id: int
    question: str
    answer: str
    had_image: bool = False
    llm_model: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CoachCard(BaseModel):
    priority: str
    title: str
    message: str


class CoachSummaryOut(BaseModel):
    cards: List[CoachCard] = Field(default_factory=list)


class LiveIntelOut(BaseModel):
    city: Optional[str] = None
    weather_condition: Optional[str] = None
    temperature_c: Optional[float] = None
    uv_index: Optional[float] = None
    aqi: Optional[int] = None
    environment_tips: List[str] = Field(default_factory=list)
    outbreak_alerts: List[str] = Field(default_factory=list)
    health_tips: List[str] = Field(default_factory=list)
    alert_level: str = "NORMAL"
    summary: Optional[str] = None
    speak_text: Optional[str] = None
    generated_at: Optional[datetime] = None
    sources: Dict[str, Any] = Field(default_factory=dict)


class DailyTaskOut(BaseModel):
    key: str
    title: str
    description: str
    target: str
    completed: bool = False


class DailyTaskUpdate(BaseModel):
    completed: bool


class DailyPlanOut(BaseModel):
    plan_date: date
    completion_ratio: float
    tasks: List[DailyTaskOut] = Field(default_factory=list)


class NotificationOut(BaseModel):
    id: int
    event_type: str
    title: str
    message: str
    severity: str
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None


class NotificationStatusUpdate(BaseModel):
    status: str
    snooze_minutes: Optional[int] = Field(default=60, ge=1, le=1440)


class EngagementOut(BaseModel):
    current_streak_days: int
    hydration_streak_days: int
    activity_streak_days: int
    weekly_score: int
    milestones: List[str] = Field(default_factory=list)


class ShareLinkCreate(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=720)
    lookback_days: int = Field(default=30, ge=1, le=365)


class ShareLinkOut(BaseModel):
    token: str
    share_url: str
    view_url: str
    pdf_url: str
    expires_at: datetime
    lookback_days: int


class OAuthStartOut(BaseModel):
    provider: str
    auth_url: str
    state: str
    expires_at: datetime


class DemoSeedOut(BaseModel):
    inserted_records: int
    inserted_risk_rows: int


class DashboardOut(BaseModel):
    risk_summary: Dict[str, Any] = Field(default_factory=dict)
    forecast: Dict[str, Any] = Field(default_factory=dict)
    trends: Dict[str, Any] = Field(default_factory=dict)
    engagement: EngagementOut
    daily_plan: DailyPlanOut
    unread_notifications: int = 0
