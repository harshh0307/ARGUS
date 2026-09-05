from app.git.base import GitProvider, GitRepo, GitPR, GitCheck
from app.git.github import GitHubProvider
from app.git.gitlab import GitLabProvider
from app.git.bitbucket import BitbucketProvider


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
