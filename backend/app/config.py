from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    collection_alert_webhook: str = Field(default='',repr=False)
    collection_alert_channel: str = 'generic'
    collection_alert_chat_id: str = Field(default='',repr=False)
    collection_exchange_token: str = Field(default='',repr=False)
    collection_peer_url: str = ''
    collection_sync_interval_minutes: int = Field(default=5,ge=1,le=1440)
    collection_sync_batch_size: int = Field(default=12,ge=1,le=32)
    public_notice_watch_enabled: bool = False
    public_notice_watch_batch_size: int = Field(default=8, ge=1, le=32)
    collector_enabled: bool = False
    collector_allowed_hosts: str = ""
    collector_skip_robots: bool = False
    dify_api_base: str = ""
    dify_app_key: str = ""
    development_dify_api_base: str = ""
    development_dify_app_key: str = ""
    demo_mode: bool = False
    supabase_url: str = ""
    supabase_anon_key: str = ""
    admin_user_ids: str = ""
    database_url: str = "sqlite:///./campusmate.db"
    @field_validator('database_url')
    @classmethod
    def postgres_driver(cls,value):
        if value.startswith(('postgres://','postgresql://')):
            return 'postgresql+psycopg://'+value.split('://',1)[1]
        return value
    cors_origins: str = "http://localhost:3000"

    # ---------------------------------------------------------------------
    # LOCAL-DEV OVERRIDE - NOT FOR PRODUCTION
    # ---------------------------------------------------------------------
    # The upstream project enforces "three-way separation" on endpoint
    # calibration: the submitter plus TWO distinct reviewers must all be
    # different admin identities, and every piece of robots/terms/licence
    # evidence must be present. That is an anti-collusion control, and it is
    # deliberately impossible to satisfy with a single administrator.
    #
    # Setting `single_admin_overrides` relaxes ONLY the identity-separation
    # part so one operator can unblock and run endpoints locally. It does NOT
    # remove the evidence requirement, and it does NOT auto-approve anything.
    # Leave it False for any shared, staged or production deployment.
    single_admin_overrides: bool = False

    # ---------------------------------------------------------------------
    # COLLECTOR ROBOTS OVERRIDE - LOCAL DEV ONLY
    # ---------------------------------------------------------------------
    # The governed collector normally refuses to fetch a URL unless
    # robots.txt allows it. That check is deliberately fail-closed, and it
    # has a real weakness: some government portals serve the whole site
    # (HTML included) on every path, so `GET /robots.txt` returns a 200 with
    # an HTML body instead of a robots file. CPython's RobotFileParser then
    # reads zero rules and reports "disallow all", which blocks endpoints
    # whose operators never actually restricted crawling.
    #
    # Setting `collector_skip_robots` skips the robots gate for the local
    # development collector. It does NOT bypass the HTTPS allowlist, the
    # public-IP pinning, the official-host redirect check, or any of the
    # calibration/evidence requirements. Leave it False in production, and
    # always prefer resolving the robots question with the site operator.
    collector_skip_robots: bool = False

    # ---------------------------------------------------------------------
    # COLLECTOR PLAINTEXT-HTTP OVERRIDE - LOCAL DEV ONLY
    # ---------------------------------------------------------------------
    # The governed collector requires HTTPS on port 443 and rejects anything
    # else, which is the right default. Some official portals, however, work
    # the other way round: www.moe.gov.cn sits behind TencentEdgeOne and
    # answers every https:// request with "302 Found -> http://..." (verified
    # 2026-09-29 for both / and /jyb_sjzl/). Their content is only reachable
    # over plaintext HTTP.
    #
    # Setting `collector_allow_plaintext_hosts` to a comma-separated hostname
    # list permits exactly those hosts to be collected over HTTP on port 80.
    # It is an explicit, per-host exception rather than a global relaxation:
    # empty means "HTTPS only everywhere", and any host not listed still
    # requires HTTPS. Because plaintext traffic is tamperable, the page
    # SHA-256 recorded on every calibration becomes the only integrity
    # anchor, so the list must stay as short as possible and must never be
    # used for anything carrying credentials or personal data.
    collector_allow_plaintext_hosts: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
