package promote

// Environment represents an environment
type Environment string

const (
	EnvironmentUnknown    Environment = ""
	EnvironmentProduction Environment = "production"
	EnvironmentStaging    Environment = "staging"
)

// GetBranch returns the branch of an environment.
func (e Environment) GetBranch() string {
	switch e {
	case EnvironmentProduction:
		// See "deploy-production.yaml" for how this gets into
		// the "prod" branch.
		return "deploy-queue/prod"
	case EnvironmentStaging:
		return "staging"
	default:
		return ""
	}
}

// GetHotfixBranch returns the hotfix branch for an environment. If an
// empty string is returned, this environment is not setup for hotfixes.
func (e Environment) GetHotfixBranch() string {
	switch e {
	case EnvironmentProduction:
		return "deploy-queue-hotfix/prod"
	default:
		return ""
	}
}

// GetDeployBranch returns the final "frozen" branch for deployments.
// This branch is only pushed too by GHA with image digests. If an empty
// string is returned, this environment only uses the branch from
// [Environment.GetBranch].
func (e Environment) GetDeployBranch() string {
	switch e {
	case EnvironmentProduction:
		return "prod"
	default:
		return ""
	}
}
