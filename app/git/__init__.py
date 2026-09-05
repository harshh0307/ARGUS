from app.git.base import GitCheck as GitCheck
from app.git.base import GitPR as GitPR
from app.git.base import GitProvider
from app.git.base import GitRepo as GitRepo
from app.git.bitbucket import BitbucketProvider
from app.git.github import GitHubProvider
from app.git.gitlab import GitLabProvider


def get_provider(settings, provider: str | None = None) -> GitProvider:
    provider = provider or getattr(settings, "git_provider", "github")
    providers = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
        "bitbucket": BitbucketProvider,
    }
    cls = providers.get(provider)
    if cls is None:
        raise ValueError(f"unknown git provider: {provider!r}; known: {', '.join(providers)}")
    return cls(settings)
