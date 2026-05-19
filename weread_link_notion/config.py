from dataclasses import dataclass
import os


def _bool_env(name, default=True):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _branch_from_ref(ref):
    if not ref:
        return ""
    return ref.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Config:
    weread_api_key: str
    notion_token: str
    notion_page: str
    github_repository: str
    github_branch: str
    skill_version: str = "1.0.3"
    heatmap_path: str = "assets/heatmap.png"
    sync_notes: bool = True
    max_notebooks: int = 0
    request_timeout: int = 30

    @classmethod
    def from_env(cls):
        ref_name = os.getenv("GITHUB_REF_NAME") or _branch_from_ref(os.getenv("GITHUB_REF"))
        return cls(
            weread_api_key=os.getenv("WEREAD_API_KEY", "").strip().strip('"').strip("'"),
            notion_token=os.getenv("NOTION_TOKEN", "").strip(),
            notion_page=os.getenv("NOTION_PAGE", "").strip(),
            github_repository=os.getenv("GITHUB_REPOSITORY") or os.getenv("REPOSITORY", ""),
            github_branch=ref_name or os.getenv("GITHUB_BRANCH", "main"),
            skill_version=os.getenv("WEREAD_SKILL_VERSION", "1.0.3").strip() or "1.0.3",
            heatmap_path=os.getenv("HEATMAP_PATH", "assets/heatmap.png").strip(),
            sync_notes=_bool_env("SYNC_NOTES", True),
            max_notebooks=_int_env("MAX_NOTEBOOKS", 0),
            request_timeout=_int_env("WEREAD_API_TIMEOUT", 30),
        )

    def validate(self):
        missing = []
        if not self.weread_api_key:
            missing.append("WEREAD_API_KEY")
        if not self.notion_token:
            missing.append("NOTION_TOKEN")
        if not self.notion_page:
            missing.append("NOTION_PAGE")
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    @property
    def heatmap_url(self):
        if not self.github_repository:
            return ""
        path = self.heatmap_path.lstrip("/")
        return f"https://raw.githubusercontent.com/{self.github_repository}/{self.github_branch}/{path}"
