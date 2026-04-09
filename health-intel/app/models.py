from sqlalchemy import Column, Integer, BigInteger, String, Date, DateTime, Float, Boolean, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime 

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    subscription_tier = Column(String, default="FREE", nullable=False)
    daily_record_limit = Column(Integer, default=10, nullable=False)
    monthly_alert_limit = Column(Integer, default=20, nullable=False)
    monthly_chat_limit = Column(Integer, default=20, nullable=False)
    monthly_image_chat_limit = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    location_permission_granted = Column(Boolean, default=False, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_label = Column(String, nullable=True)
    location_updated_at = Column(DateTime, nullable=True)

    password_hash = Column(String, nullable=False)
    login_otp_required = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    
    health_records = relationship("HealthRecord", back_populates="user")



class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    risk_score = Column(Float)
    risk_level = Column(String)
    model_version = Column(String)
    predicted_at = Column(DateTime(timezone=True), server_default=func.now())

class HealthRecord(Base):
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    record_date = Column(Date, nullable=False)
    systolic_bp = Column(Float)
    diastolic_bp = Column(Float)
    bmi = Column(Float)
    blood_glucose = Column(Float)
    cholesterol = Column(Float)
    smoking_status = Column(String)
    activity_level = Column(String)
    steps_count = Column(Integer, nullable=True)
    activity_minutes = Column(Integer, nullable=True)
    resting_heart_rate = Column(Float, nullable=True)
    hydration_liters = Column(Float, nullable=True)
    city = Column(String, nullable=True)
    weather_condition = Column(String, nullable=True)
    temperature_c = Column(Float, nullable=True)
    uv_index = Column(Float, nullable=True)
    aqi = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="health_records")


class RiskHistory(Base):
    __tablename__ = "risk_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    trend = Column(String, nullable=True)
    alert_triggered = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False, index=True)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    entry_date = Column(Date, nullable=False, index=True)
    meal_type = Column(String, nullable=True)
    calories = Column(Integer, nullable=True)
    water_liters = Column(Float, nullable=True)
    symptoms = Column(Text, nullable=True)
    goals = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    url = Column(String, nullable=False)
    events_csv = Column(String, nullable=False, default="health_record.ingested,risk.alert_triggered")
    signing_secret = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    had_image = Column(Boolean, default=False, nullable=False)
    llm_model = Column(String, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PushDevice(Base):
    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    provider = Column(String, default="fcm", nullable=False)
    platform = Column(String, nullable=False)
    device_label = Column(String, nullable=True)
    push_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)


class WearableConnection(Base):
    __tablename__ = "wearable_connections"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    provider = Column(String, nullable=False, index=True)
    external_user_id = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    scope = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DailyPlanCheck(Base):
    __tablename__ = "daily_plan_checks"
    __table_args__ = (UniqueConstraint("user_id", "plan_date", "task_key", name="uq_daily_plan_check"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    plan_date = Column(Date, index=True, nullable=False)
    task_key = Column(String, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    event_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String, nullable=False, default="INFO")
    status = Column(String, nullable=False, default="NEW")
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    snoozed_until = Column(DateTime, nullable=True)


class ShareLink(Base):
    __tablename__ = "share_links"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    lookback_days = Column(Integer, nullable=False, default=30)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    provider = Column(String, nullable=False)
    state = Column(String, nullable=False, unique=True, index=True)
    code_verifier = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LoginVerificationCode(Base):
    __tablename__ = "login_verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    challenge_id = Column(String, nullable=False, unique=True, index=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    is_used = Column(Boolean, nullable=False, default=False)
    delivery_channel = Column(String, nullable=False, default="email")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    consumed_at = Column(DateTime, nullable=True)


class StepSensorState(Base):
    __tablename__ = "step_sensor_states"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_step_sensor_state_user_device"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    device_id = Column(String, nullable=False)
    sensor_type = Column(String, nullable=False, default="STEP_COUNTER")
    timezone_name = Column(String, nullable=True)
    last_boot_id = Column(String, nullable=True)
    baseline_date = Column(Date, nullable=True)
    baseline_total_since_boot = Column(BigInteger, nullable=True)
    last_total_since_boot = Column(BigInteger, nullable=True)
    daily_steps = Column(Integer, nullable=False, default=0)
    last_sync_mode = Column(String, nullable=True)
    algorithm_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    last_event_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
